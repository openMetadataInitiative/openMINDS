import json
import os
import re
from typing import List

from generator.commons import SchemaStructure, TEMPLATE_PROPERTY_TYPE


def _camel_case_to_human_readable(value:str):
    return re.sub("([a-z])([A-Z])","\g<1> \g<2>",value).capitalize()


class VocabEnrichment(object):

    @staticmethod
    def enrich_with_vocab( types_file, properties_file, schemas: List[SchemaStructure], vocab_prefix:str):
        with open(types_file, "r") as types_file_path:
            types = json.load(types_file_path)
        with open(properties_file, "r") as properties_file_path:
            properties = json.load(properties_file_path)
        for schema_info in schemas:
            print(f"Enriching schema {schema_info.file}")
            with open(schema_info.absolute_path, "r") as schema_file:
                schema = json.load(schema_file)
            type = schema[TEMPLATE_PROPERTY_TYPE]
            if type in types:
                t = types[type]
                if "deprecated" in t and t["deprecated"]:
                    schema["_deprecated"] = True
                if "description" in t and t["description"]:
                    schema["description"] = t["description"]
                if "name" in t and t["name"]:
                    schema["title"] = t["name"]
            if "properties" in schema:
                for p in schema["properties"]:
                    qualified_p = f"{vocab_prefix}{p}"
                    if qualified_p in properties:
                        prop = properties[qualified_p]
                        if "description" in prop and prop["description"]:
                            schema["properties"][p]["description"] = prop["description"]
                        if "name" in prop and prop["name"]:
                            schema["properties"][p]["title"] = prop["name"]
                        if "sameAs" in prop and prop["sameAs"]:
                            schema["properties"][p]["_sameAs"] = prop["sameAs"]
            with open(schema_info.absolute_path, "w") as schema_file:
                schema_file.write(json.dumps(schema, indent=4))



class VocabExtractor(object):

    def __init__(self, schema_information:List[SchemaStructure], root_path, reinit, current_version, vocab):
        self.schema_information = schema_information
        self.root_path = os.path.realpath(root_path)
        self.vocab_path = os.path.join(self.root_path, "vocab")
        self.properties_file = os.path.join(self.vocab_path, "properties.json")
        self.types_file = os.path.join(self.vocab_path, "types.json")
        self.properties_version_file = os.path.join(self.root_path, f"properties-{current_version}.json")
        self.types_version_file = os.path.join(self.root_path, f"types-{current_version}.json")
        self.vocab = vocab
        self.reinit = reinit
        self.version_specific_properties = {}
        self.version_specific_types = {}

    def _load_properties(self):
        if os.path.exists(self.properties_file):
            with open(self.properties_file, "r") as properties_f:
                self.properties = json.load(properties_f)
            if self.reinit:
                for p in self.properties:
                    # We want to make sure that only current (not previously existing) schema definitions are reported. This is why we need to clear the array first
                    self.properties[p]["schemas"] = []
        else:
            self.properties = {}

    def _load_types(self):
        if os.path.exists(self.types_file):
            with open(self.types_file, "r") as types_f:
                self.types = json.load(types_f)
            if self.reinit:
                for t in self.types:
                    self.types[t]["schemas"] = []
        else:
            self.types = {}

    def _handle_property(self, p, schema):
        qualified_p = f"{self.vocab}{p}"
        if qualified_p not in self.properties:
            self.properties[qualified_p] = {"label": _camel_case_to_human_readable(p), "description": None, "schemas": [], "linkedTypes": [], "sameAs": []}
        self.properties[qualified_p]["name"] = p
        if "schemas" not in self.properties[qualified_p] or not self.properties[qualified_p]["schemas"]:
            self.properties[qualified_p]["schemas"] = []
        self.properties[qualified_p]["schemas"].append(schema)
        self.properties[qualified_p]["schemas"] = sorted(set(self.properties[qualified_p]["schemas"]))
        self.version_specific_properties[qualified_p] = self.properties[qualified_p]

    def _handle_type(self, type, schema):
        if type not in self.types:
            self.types[type] = {"label": _camel_case_to_human_readable(os.path.basename(type)), "description": None, "translatableTo": None, "schemas": []}
        if "schemas" not in self.types[type] or not self.types[type]["schemas"]:
            self.types[type]["schemas"] = []
        self.types[type]["schemas"].append(schema)
        self.types[type]["schemas"] = sorted(set(self.types[type]["schemas"]))
        self.version_specific_types[type] = self.types[type]

    def _clear_schema_information(self, map):
        for k in map:
            if "schemas" in map[k]:
                del map[k]["schemas"]

    def extract(self):
        self._load_types()
        self._load_properties()
        for schema_info in self.schema_information:
            with open(schema_info.absolute_path, "r") as schema_file:
                schema = json.load(schema_file)
            type = schema[TEMPLATE_PROPERTY_TYPE]
            self._handle_type(type, schema_info.get_schema_name())
            if "properties" in schema:
                for p in schema["properties"]:
                    self._handle_property(p, schema_info.get_schema_name())
        with open(self.types_file, "w+") as types_f:
            types_f.write(json.dumps(self.types, sort_keys=True, indent=4))
        with open(self.properties_file, "w+") as properties_f:
            properties_f.write(json.dumps(self.properties, sort_keys=True, indent=4))
        self._clear_schema_information(self.version_specific_types)
        with open(self.types_version_file, "w+") as types_version_f:
            types_version_f.write(json.dumps(self.version_specific_types, sort_keys=True, indent=4))
        self._clear_schema_information(self.version_specific_properties)
        with open(self.properties_version_file, "w+") as properties_version_f:
            properties_version_f.write(json.dumps(self.version_specific_properties, sort_keys=True, indent=4))
        return self.types_file, self.properties_file
