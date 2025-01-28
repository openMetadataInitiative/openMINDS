import json
import os
import re
from typing import List, Dict

from openMINDS_pipeline.models import DirectoryStructure, SchemaStructure
from openMINDS_pipeline.resolver import TEMPLATE_PROPERTY_TYPE
from openMINDS_pipeline.utils import get_basic_type, is_edge
from openMINDS_pipeline.constants import FIRST_VERSION


def _camel_case_to_human_readable(value: str):
    return re.sub("([a-z])([A-Z])", "\g<1> \g<2>", value).capitalize()


def enrich_with_types_and_properties(types, properties, schemas: List[SchemaStructure]):
   for schema_info in schemas:
        print(f"Enriching schema {schema_info.file}")
        with open(schema_info.absolute_path, "r") as schema_file:
            schema = json.load(schema_file)
        type = schema[TEMPLATE_PROPERTY_TYPE].split(":")[-1].split("/")[-1]
        if type in types:
            _enrich_with_type_information(schema, type, types)

        if "properties" in schema:
            for p in schema["properties"]:
                property_with_namespace = p
                p = p.split('/')[-1]
                _enrich_with_property_information(schema_info.version, p, properties, schema, property_with_namespace)
        with open(schema_info.absolute_path, "w") as schema_file:
            schema_file.write(json.dumps(schema, indent=2, sort_keys=True))


def _enrich_with_property_information(version: str, p, properties, schema, property_with_namespace):
    if p in properties:
        prop = properties[p]
        if "description" in prop and prop["description"]:
            schema["properties"][property_with_namespace]["description"] = prop["description"]
        if "label" in prop and prop["label"]:
            schema["properties"][property_with_namespace]["label"] = prop["label"]
        if "labelPlural" in prop and prop["labelPlural"]:
            schema["properties"][property_with_namespace]["labelPlural"] = prop["labelPlural"]
        if "name" in prop and prop["name"]:
            schema["properties"][property_with_namespace]["name"] = prop["name"]
        if "namePlural" in prop and prop["namePlural"]:
            schema["properties"][property_with_namespace]["namePlural"] = prop["namePlural"]

        embedded_types, linked_types, edge = is_edge(schema["properties"][property_with_namespace])
        if edge and "asEdge" in prop:
            for k, v in prop["asEdge"].items():
                if k != "canPointTo":
                    schema["properties"][property_with_namespace][k] = v
        basic_type = get_basic_type(schema["properties"][property_with_namespace])
        if basic_type == "string" and "asString" in prop:
            for k, v in prop["asString"].items():
                if k != "inVersions":
                    schema["properties"][property_with_namespace][k] = v

def _enrich_with_type_information(schema, type, types):
    t = types[type]
    if "description" in t and t["description"]:
        schema["description"] = t["description"]
    if "name" in t and t["name"]:
        schema["name"] = t["name"]
    if "label" in t and t["label"]:
        schema["label"] = t["label"]
    if "color" in t and t["color"]:
        schema["color"] = t["color"]


def enrich_types_with_identical(vocab_types: Dict, changed_types: Dict[str, int], previous_version: str, current_version: str, iteration: int):
    def extend_or_sort_identical(vocab_entry, current_version: str):
        """ Helper function to handle sorting of versions in the 'identical' field."""
        if "identical" in vocab_entry:
            vocab_entry["identical"][-1].append(current_version)
            vocab_entry["identical"][-1].sort()
        else:
            vocab_entry.setdefault("identical", []).append([current_version])

    for _type in vocab_types:
        # Handle the first iteration (comparison with v1.0)
        if previous_version == FIRST_VERSION and previous_version in vocab_types[_type].get("isPartOfVersion"):
            vocab_types[_type].setdefault("identical", []).append([previous_version])

        # Update based on changed types
        if _type in changed_types:
            vocab_types[_type].setdefault("identical", []).append([current_version])
        elif current_version in vocab_types[_type].get("isPartOfVersion"):
            extend_or_sort_identical(vocab_types[_type], current_version)


class Types(object):

    def __init__(self, directory_structure: DirectoryStructure):
        self._types_file = os.path.join(directory_structure.target_directory, "vocab", "types.json")
        self._types = self._load_types()

    def _load_types(self):
        if os.path.exists(self._types_file):
            with open(self._types_file, "r") as types_f:
                _types = json.load(types_f)
                _type_names = {}
                for source_type in _types:
                    # remove namespace
                    _type_names[source_type.split(":")[-1].split("/")[-1]] = _types[source_type]
                return _type_names
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
        self._namespaces = None

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
        self._namespaces = schema.namespaces

        with open(schema.absolute_path, "r") as schema_file:
            schema_payload = json.load(schema_file)
        # Remove the namespace of the type
        t = schema_payload[TEMPLATE_PROPERTY_TYPE].split(":")[-1].split("/")[-1]

        if t in self._types:
            for k in list(self._types[t].keys()):
                if k not in ["label", "labelPlural", "name", "namePlural", "description", "isPartOfVersion", "color", "hasNamespace"]:
                    del self._types[t][k]
        simple_name = os.path.basename(t)
        if t not in self._types:
            self._types[t] = {}

        # properties to be manually edited
        if "description" not in self._types[t]:
            self._types[t]["description"] = None
        if "color" not in self._types[t]:
            self._types[t]["color"] = None

        # properties to be solely managed by the automation
        self._types[t]["label"] = _camel_case_to_human_readable(simple_name)
        self._types[t]["name"] = simple_name
        if "isPartOfVersion" not in self._types[t]:
            self._types[t]["isPartOfVersion"] = []
        if self._version not in self._types[t]["isPartOfVersion"]:
            self._types[t]["isPartOfVersion"].append(self._version)
            self._types[t]["isPartOfVersion"].sort()

        # replace by the module name in the versions prior to v4.0
        schema_group_normalized = schema.schema_group.lower() if schema.schema_group.isupper() else schema.schema_group
        type_namespace= self._namespaces['types'].replace('{MODULE}', schema_group_normalized)
        if "hasNamespace" not in self._types[t]:
            self._types[t]["hasNamespace"] = []
            self._types[t]["hasNamespace"].append({'namespace': type_namespace,
                                                   'inVersions': [self._version]})

        tmp_namespaces = []
        for x in self._types[t]["hasNamespace"]:
            tmp_namespaces.append(x["namespace"])
            if self._namespaces['types'].replace('{MODULE}', schema_group_normalized) == x["namespace"] and self._version not in x["inVersions"]:
                x["inVersions"].append(self._version)
        if type_namespace not in tmp_namespaces:
            self._types[t]["hasNamespace"].append({'namespace': type_namespace,
                                                   'inVersions': [self._version]})
        # Sort the 'hasNamespace' list based on 'inVersions'
        self._types[t]["hasNamespace"].sort(key=lambda x: sorted(x["inVersions"]))
        return t


class Property(object):

    def __init__(self, directory_structure: DirectoryStructure):
        self._properties_file = os.path.join(directory_structure.target_directory, "vocab", "properties.json")
        self._properties = self._load_properties()

    def _load_properties(self):
        if os.path.exists(self._properties_file):
            with open(self._properties_file, "r") as properties_f:
                _properties = json.load(properties_f)
                _properties_names = {}
                for source_property in _properties:
                    # remove namespace, not necessary to check for ':' here (only done for types).
                    cleaned_property = source_property.split('/')[-1]
                    _properties_names[cleaned_property] = _properties[source_property]
                return _properties_names
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
        self._namespaces = None

    def _extract_properties_for_schema(self, schema: SchemaStructure):
        self._namespaces = schema.namespaces
        with open(schema.absolute_path, "r") as schema_file:
            schema_payload = json.load(schema_file)
        t = schema_payload[TEMPLATE_PROPERTY_TYPE]
        if "properties" in schema_payload:
            for p, v in schema_payload["properties"].items():
                # remove namespace, not necessary to check for ':' here (only done for types).
                p = p.split('/')[-1]
                self._extract_property(t, p, v)

    def _extract_property(self, type: str, property: str, definition: dict):
        if property not in self._properties:
            self._properties[property] = {}
        prop = self._properties[property]
        # Clear all unexpected fields
        for k in list(prop.keys()):
            if k not in ["label", "labelPlural", "name", "namePlural", "description", "asEdge", "asString", "usedIn", "hasNamespace"]:
                del prop[k]

        # Set default values for manually managed properties
        if "description" not in prop:
            prop["description"] = None
        if "labelPlural" not in prop:
            prop["labelPlural"] = None
        if "namePlural" not in prop:
            prop["namePlural"] = None

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

        if "hasNamespace" not in prop:
            prop["hasNamespace"] = []
            prop["hasNamespace"].append({'namespace': self._namespaces['props'],
                                                   'inVersions': [self._version]})

        tmp_namespaces = []
        for x in prop["hasNamespace"]:
            tmp_namespaces.append(x["namespace"])
            if self._namespaces['props'] == x["namespace"] and self._version not in x["inVersions"]:
                x["inVersions"].append(self._version)
        if self._namespaces['props'] not in tmp_namespaces:
            prop["hasNamespace"].append({'namespace': self._namespaces['props'],
                                                   'inVersions': [self._version]})
        # Sort the 'hasNamespace' list based on 'inVersions'
        prop["hasNamespace"].sort(key=lambda x: sorted(x["inVersions"]))

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
