import json
import os
import re
from typing import List

from openMINDS_pipeline.models import DirectoryStructure, SchemaStructure
from openMINDS_pipeline.resolver import TEMPLATE_PROPERTY_TYPE
from openMINDS_pipeline.utils import get_basic_type, is_edge


def _camel_case_to_human_readable(value: str):
    return re.sub("([a-z])([A-Z])", "\g<1> \g<2>", value).capitalize()


def enrich_with_types_and_properties(version: str, types, properties, schemas: List[SchemaStructure]):
    for schema_info in schemas:
        print(f"Enriching schema {schema_info.file}")
        with open(schema_info.absolute_path, "r") as schema_file:
            schema = json.load(schema_file)
        type = schema[TEMPLATE_PROPERTY_TYPE]
        if type in types:
            _enrich_with_type_information(schema, type, types)
        if "properties" in schema:
            for p in schema["properties"]:
                _enrich_with_property_information(version, p, properties, schema)
        with open(schema_info.absolute_path, "w") as schema_file:
            schema_file.write(json.dumps(schema, indent=2, sort_keys=True))


def _enrich_with_property_information(version: str, p, properties, schema):
    if p in properties:
        prop = properties[p]
        if "description" in prop and prop["description"]:
            schema["properties"][p]["description"] = prop["description"]
        if "name" in prop and prop["name"]:
            schema["properties"][p]["name"] = prop["name"]
        if "label" in prop and prop["label"]:
            schema["properties"][p]["label"] = prop["label"]
        if "semanticEquivalent" in prop and prop["semanticEquivalent"]:
            schema["properties"][p]["semanticEquivalent"] = prop["semanticEquivalent"]

        embedded_types, linked_types, edge = is_edge(schema["properties"][p])
        if edge and "asEdge" in prop:
            for k, v in prop["asEdge"].items():
                if k != "canPointTo":
                    schema["properties"][p][k] = v
        basic_type = get_basic_type(schema["properties"][p])
        if basic_type == "string" and "asString" in prop:
            for k, v in prop["asString"].items():
                if k != "inVersions":
                    schema["properties"][p][k] = v


def _enrich_with_type_information(schema, type, types):
    t = types[type]
    if "description" in t and t["description"]:
        schema["description"] = t["description"]
    if "name" in t and t["name"]:
        schema["name"] = t["name"]
    if "label" in t and t["label"]:
        schema["label"] = t["label"]
    if "semanticEquivalent" in t and t["semanticEquivalent"]:
        schema["semanticEquivalent"] = t["semanticEquivalent"]
    if "color" in t and t["color"]:
        schema["color"] = t["color"]


class Types(object):

    def __init__(self, directory_structure: DirectoryStructure):
        self._types_file = os.path.join(directory_structure.target_directory, "vocab", "types.json")
        self._types = self._load_types()

    def _load_types(self):
        if os.path.exists(self._types_file):
            with open(self._types_file, "r") as types_f:
                return json.load(types_f)
        else:
            return {}

    def _save_types(self):
        with open(self._types_file, "w+") as types_file:
            types_file.write(json.dumps(self._types, sort_keys=True, indent=2))

    def clean_types(self):
        to_be_removed = []
        for t, v in self._types.items():
            if "isPartOfVersion" not in v or not v["isPartOfVersion"]:
                to_be_removed.append(t)
        if to_be_removed:
            print(f"Removing {len(to_be_removed)} types because they are not included in any version ({json.dumps(to_be_removed)}")
            for remove in to_be_removed:
                del self._types[remove]
            self._save_types()


class TypeExtractor(Types):

    def __init__(self, directory_structure: DirectoryStructure, version: str):
        super().__init__(directory_structure)
        self._version = version

    def extract_types(self, schemas) -> dict:
        new_types = []
        types_in_version = []
        for k, v in self._types.items():
            if "isPartOfVersion" in v and self._version in v["isPartOfVersion"]:
                types_in_version.append(k)
                v["isPartOfVersion"].remove(self._version)
        for schema in schemas:
            type = self._extract_type(schema)
            if type in types_in_version:
                types_in_version.remove(type)
            else:
                new_types.append(type)
        if len(new_types):
            print(f"Attention: {len(new_types)} schema(s) have been added to version {self._version} in this run")
        if len(types_in_version):
            print(f"Attention: {len(types_in_version)} schema(s) have been removed from version {self._version} in this run ({json.dumps(types_in_version)}")
        self._save_types()
        return self._types

    def _extract_type(self, schema: SchemaStructure) -> str:
        with open(schema.absolute_path, "r") as schema_file:
            schema_payload = json.load(schema_file)
        t = schema_payload[TEMPLATE_PROPERTY_TYPE]
        if t in self._types:
            for k in list(self._types[t].keys()):
                if k not in ["label", "name", "description", "semanticEquivalent", "isPartOfVersion", "color"]:
                    del self._types[t][k]
        simple_name = os.path.basename(t)
        if t not in self._types:
            self._types[t] = {}

        # properties to be manually edited
        if "description" not in self._types[t]:
            self._types[t]["description"] = None
        if "color" not in self._types[t]:
            self._types[t]["color"] = None
        if "semanticEquivalent" not in self._types[t]:
            self._types[t]["semanticEquivalent"] = []
        self._types[t]["semanticEquivalent"].sort()

        # properties to be solely managed by the automation
        self._types[t]["label"] = _camel_case_to_human_readable(simple_name)
        self._types[t]["name"] = simple_name
        if "isPartOfVersion" not in self._types[t]:
            self._types[t]["isPartOfVersion"] = []
        if self._version not in self._types[t]["isPartOfVersion"]:
            self._types[t]["isPartOfVersion"].append(self._version)
            self._types[t]["isPartOfVersion"].sort()
        return t


class Property(object):

    def __init__(self, directory_structure: DirectoryStructure):
        self._properties_file = os.path.join(directory_structure.target_directory, "vocab", "properties.json")
        self._properties = self._load_properties()

    def _load_properties(self):
        if os.path.exists(self._properties_file):
            with open(self._properties_file, "r") as properties_f:
                return json.load(properties_f)
        else:
            return {}

    def _save_properties(self):
        with open(self._properties_file, "w+") as properties_file:
            properties_file.write(json.dumps(self._properties, sort_keys=True, indent=2))

    def clean_properties(self):
        to_be_removed = []
        for p, v in self._properties.items():
            if "usedIn" not in v or not v["usedIn"]:
                to_be_removed.append(p)
        if to_be_removed:
            print(f"Removing {len(to_be_removed)} properties because they are not included in any version ({json.dumps(to_be_removed)}")
            for remove in to_be_removed:
                del self._properties[remove]
            self._save_properties()


class PropertyExtractor(Property):

    def __init__(self, directory_structure: DirectoryStructure, version: str):
        super().__init__(directory_structure)
        self._version = version

    def _extract_properties_for_schema(self, schema: SchemaStructure):
        with open(schema.absolute_path, "r") as schema_file:
            schema_payload = json.load(schema_file)
        t = schema_payload[TEMPLATE_PROPERTY_TYPE]
        if "properties" in schema_payload:
            for p, v in schema_payload["properties"].items():
                self._extract_property(t, p, v)

    def _extract_property(self, type: str, property: str, definition: dict):
        if property not in self._properties:
            self._properties[property] = {}
        prop = self._properties[property]

        # Clear all unexpected fields
        for k in list(prop.keys()):
            if k not in ["label", "name", "description", "semanticEquivalent", "asEdge", "asString", "usedIn"]:
                del prop[k]

        # Set default values for manually managed properties
        if "description" not in prop:
            prop["description"] = None
        if "semanticEquivalent" not in prop:
            prop["semanticEquivalent"] = []
        prop["semanticEquivalent"].sort()

        # Automatically calculated values
        unqualified_property = os.path.basename(property)
        prop["label"] = _camel_case_to_human_readable(unqualified_property)
        prop["name"] = unqualified_property

        if "usedIn" not in prop:
            prop["usedIn"] = {}
        if self._version not in prop["usedIn"]:
            prop["usedIn"][self._version] = []
        prop["usedIn"][self._version].append(type)
        prop["usedIn"][self._version].sort()

        embedded_types, linked_types, edge = is_edge(definition)
        if edge:
            if "asEdge" not in prop:
                prop["asEdge"] = {}
            if "nameForReverseLink" not in prop["asEdge"]:
                prop["asEdge"]["nameForReverseLink"] = None
            if "canPointTo" not in prop["asEdge"]:
                prop["asEdge"]["canPointTo"] = {}
            if self._version not in prop["asEdge"]["canPointTo"]:
                prop["asEdge"]["canPointTo"][self._version] = []
            if linked_types:
                prop["asEdge"]["canPointTo"][self._version].extend(linked_types)
            if embedded_types:
                prop["asEdge"]["canPointTo"][self._version].extend(embedded_types)
            prop["asEdge"]["canPointTo"][self._version] = list(set(prop["asEdge"]["canPointTo"][self._version]))
            prop["asEdge"]["canPointTo"][self._version].sort()
            name_for_reverse_link = prop["asEdge"]["nameForReverseLink"] if "nameForReverseLink" in prop["asEdge"] else None
            if name_for_reverse_link:
                prop["asEdge"]["labelForReverseLink"] = _camel_case_to_human_readable(name_for_reverse_link)

        basic_type = get_basic_type(definition)

        if basic_type == "string":
            if "asString" not in prop:
                prop["asString"] = {}
            if "inVersions" not in prop["asString"]:
                prop["asString"]["inVersions"] = []
            if self._version not in prop["asString"]["inVersions"]:
                prop["asString"]["inVersions"].append(self._version)
                prop["asString"]["inVersions"].sort()
            if "formatting" not in prop["asString"]:
                prop["asString"]["formatting"] = "text/plain"
            if "multiline" not in prop["asString"]:
                prop["asString"]["multiline"] = False

    def extract_properties(self, schemas) -> dict:
        self._load_properties()
        self._clear_current_version()
        for schema in schemas:
            self._extract_properties_for_schema(schema)
        self._save_properties()
        return self._properties

    def _clear_current_version(self):
        for p, v in self._properties.items():
            if "usedIn" in v and self._version in v["usedIn"]:
                del v["usedIn"][self._version]
            if "asString" in v and "inVersions" in v["asString"]:
                if self._version in v["asString"]["inVersions"]:
                    v["asString"]["inVersions"].remove(self._version)
            if "asEdge" in v and "canPointTo" in v["asEdge"]:
                if self._version in v["asEdge"]["canPointTo"]:
                    del v["asEdge"]["canPointTo"][self._version]
                if not v["asEdge"]["canPointTo"]:
                    del v["asEdge"]
