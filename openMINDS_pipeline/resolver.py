import json
import os
from json import JSONDecodeError
from typing import List, Dict


from openMINDS_pipeline.models import SchemaStructure, DirectoryStructure

TEMPLATE_PROPERTY_TYPE = "_type"
TEMPLATE_PROPERTY_EXTENDS = "_extends"
TEMPLATE_PROPERTY_LINKED_TYPES = "_linkedTypes"
TEMPLATE_PROPERTY_EMBEDDED_TYPES = "_embeddedTypes"
TEMPLATE_PROPERTY_FORMATS = "_formats"
TEMPLATE_PROPERTY_CATEGORIES = "_categories"
TEMPLATE_PROPERTY_LINKED_CATEGORIES = "_linkedCategories"
TEMPLATE_PROPERTY_EMBEDDED_CATEGORIES = "_embeddedCategories"
TEMPLATE_PROPERTY_MODULE = "_module"


def resolve_extends(schemas: List[SchemaStructure], directory_structure: DirectoryStructure):
    for schema in schemas:
        try:
            absolute_schema_group_target_dir = directory_structure.expanded_schema_directory(schema)
            absolute_schema_group_src_dir = directory_structure.source_schema_directory(schema.schema_group)
            print(f"extending {schema.file}")
            with open(os.path.join(absolute_schema_group_src_dir, schema.file), "r") as schema_file:
                schema_payload = json.load(schema_file)
            schema_target_path = os.path.join(absolute_schema_group_target_dir, schema.file)
            _do_resolve_extends(schema, schema_payload, schema.schema_group, directory_structure)
            schema.set_absolute_path(schema_target_path)
            os.makedirs(os.path.dirname(schema_target_path), exist_ok=True)
            with open(schema_target_path, "w") as target_file:
                target_file.write(json.dumps(schema_payload, indent=2, sort_keys=True))
        except JSONDecodeError:
            print(f"Skipping schema {schema.file} because it is not a valid JSON document")


def resolve_categories(version:str, directory_structure: DirectoryStructure, schemas: List[SchemaStructure]):
    categories = _load_categories(directory_structure)
    if version in categories:
        del categories[version]
    schemas_by_category = _schemas_by_category(schemas)
    for schema in schemas:
        print(f"resolving categories for {schema.type}")
        _do_resolve_categories(version, schema, schemas_by_category)
    categories[version] = schemas_by_category
    _save_categories(directory_structure, categories)


def _load_categories(directory_structure: DirectoryStructure):
    categories_file = os.path.join(directory_structure.target_directory, "vocab", "categories.json")
    if os.path.exists(categories_file):
        with open(categories_file, "r") as categories_f:
            return json.load(categories_f)
    else:
        return {}


def _save_categories(directory_structure, categories):
    categories_file = os.path.join(directory_structure.target_directory, "vocab", "categories.json")
    with open(categories_file, "w+") as categories_f:
        categories_f.write(json.dumps(categories, sort_keys=True, indent=2))


def _schemas_by_category(schemas: List[SchemaStructure]) -> Dict[str, List[str]]:
    """
    :returns a lookup dictionary which types belong to a given category
    """
    result = {}
    for s in schemas:
        if s.categories:
            for c in s.categories:
                if c not in result:
                    result[c] = []
                # lowercase "acronym"-alike modules
                schema_group_normalized = s.schema_group.lower() if s.schema_group.isupper() else s.schema_group
                result[c].append(schema_group_normalized + ':' + s.type)
                result[c].sort()
    return result


def _do_resolve_extends(source_schema, schema, schema_group, directory_structure: DirectoryStructure):
    # Autocomplete with the correct namespace, just rebuild it for older versions (replace part)
    if TEMPLATE_PROPERTY_TYPE in schema:
        schema_group_normalized = source_schema.schema_group.lower() if source_schema.schema_group.isupper() else source_schema.schema_group
        schema[TEMPLATE_PROPERTY_TYPE] = source_schema.namespaces['types'].replace('{MODULE}',
                                                                               schema_group_normalized) + \
                                     schema[TEMPLATE_PROPERTY_TYPE].split(":")[-1].split("/")[-1]
        # Add schema module
        schema[TEMPLATE_PROPERTY_MODULE] = source_schema.schema_group

    if TEMPLATE_PROPERTY_EXTENDS in schema:
        if schema[TEMPLATE_PROPERTY_EXTENDS].startswith("/"):
            extends_split = schema[TEMPLATE_PROPERTY_EXTENDS].split("/")
            extension_schema_group = extends_split[1]
            # For cross-submodule references, we allow the schemas to declare "absolute" paths which need to be relativated against the processing directory in this step.
            extension_path = os.path.join(directory_structure.source_directory, schema[TEMPLATE_PROPERTY_EXTENDS][1:])
        else:
            extension_schema_group = schema_group
            extension_path = os.path.join(directory_structure.source_schema_directory(schema_group), schema[TEMPLATE_PROPERTY_EXTENDS])
        if directory_structure.is_part_of_working_directory(extension_path):
            # Only load the extension if it is part of the same schema group (and if it exists)
            # (prevent access of resources outside of the directory structure)
            with open(extension_path, "r") as extension_file:
                extension = json.load(extension_file)
            # We need to extend the extension itself first to ensure that we can handle multi-level extensions...
            extended_schema = _do_resolve_extends(source_schema, extension, extension_schema_group, directory_structure)
            _apply_extension(schema, extended_schema)
        del schema[TEMPLATE_PROPERTY_EXTENDS]
    if TEMPLATE_PROPERTY_CATEGORIES in schema and schema[TEMPLATE_PROPERTY_CATEGORIES]:
        source_schema.set_categories(schema[TEMPLATE_PROPERTY_CATEGORIES])
    return schema


def _apply_extension(source, extension):
    # Required has to be a list...
    if "required" in extension:
        if "required" not in source:
            source["required"] = extension["required"]
        elif type(source["required"]) is list and type(extension["required"]) is list:
            source["required"] = list(set(source["required"] + extension["required"]))
    if "properties" not in source:
        source["properties"] = {}

    if TEMPLATE_PROPERTY_CATEGORIES in extension:
        if TEMPLATE_PROPERTY_CATEGORIES not in source:
            source[TEMPLATE_PROPERTY_CATEGORIES] = sorted(extension[TEMPLATE_PROPERTY_CATEGORIES])
        elif type(source[TEMPLATE_PROPERTY_CATEGORIES]) is list and type(extension[TEMPLATE_PROPERTY_CATEGORIES]) is list:
            source[TEMPLATE_PROPERTY_CATEGORIES] = sorted(list(set(source[TEMPLATE_PROPERTY_CATEGORIES] + extension[TEMPLATE_PROPERTY_CATEGORIES])))

    for k in extension["properties"]:
        property_from_extension = extension["properties"][k]
        if k in source["properties"]:
            property_from_source = source["properties"][k]
            for property_spec_key in property_from_extension:
                # Only apply the specification element from the extension if it doesn't yet exist in the source
                if property_spec_key not in property_from_source:
                    property_from_source[property_spec_key] = property_from_extension[property_spec_key]
        else:
            # If the property is not in the source yet at all, we add it as a whole from the extension
            source["properties"][k] = extension["properties"][k]


def _do_resolve_categories(version: str, schema: SchemaStructure, schemas_by_category):

    def _namespace_completion_categories(schema_payload, schema, p, template_property):
        def _build_namespace_type(_type):
            # if _type is an URI rebuild it
            # else _type consists of prefix:name_type
            module = _type.split("/")[-2] if '/' in _type else _type.split(":")[0]
            name_type = _type.split("/")[-1] if '/' in _type else _type.split(":")[-1]
            return schema.namespaces['types'].replace('{MODULE}', module) + name_type

        schema_payload["properties"][p][template_property] = [
            _build_namespace_type(_type) for _type in schema_payload["properties"][p][template_property]]
        return schema_payload

    with open(schema.absolute_path, "r") as schema_file:
        schema_payload = json.load(schema_file)
    if "properties" in schema_payload:
        for p in schema_payload["properties"]:
            if TEMPLATE_PROPERTY_LINKED_CATEGORIES in schema_payload["properties"][p]:
                linked_categories = schema_payload["properties"][p][TEMPLATE_PROPERTY_LINKED_CATEGORIES]
                linked_types = []
                for linked_category in linked_categories:
                    if linked_category in schemas_by_category:
                        linked_types.extend(schemas_by_category[linked_category])
                schema_payload["properties"][p][TEMPLATE_PROPERTY_LINKED_TYPES] = sorted(linked_types)
                schema_payload["properties"][p]["_belongsToCategory"] = schema_payload["properties"][p].pop(TEMPLATE_PROPERTY_LINKED_CATEGORIES)
            if TEMPLATE_PROPERTY_EMBEDDED_CATEGORIES in schema_payload["properties"][p]:
                embedded_categories = schema_payload["properties"][p][TEMPLATE_PROPERTY_EMBEDDED_CATEGORIES]
                embedded_types = []
                for embedded_category in embedded_categories:
                    if embedded_category in schemas_by_category:
                        embedded_types.extend(schemas_by_category[embedded_category])
                schema_payload["properties"][p][TEMPLATE_PROPERTY_EMBEDDED_TYPES] = sorted(embedded_types)
                del schema_payload["properties"][p][TEMPLATE_PROPERTY_EMBEDDED_CATEGORIES]

            # Write namespace for '_linkedTypes' and '_embeddedTypes'
            if TEMPLATE_PROPERTY_LINKED_TYPES in schema_payload["properties"][p]:
                _namespace_completion_categories(schema_payload, schema, p, TEMPLATE_PROPERTY_LINKED_TYPES)

            if TEMPLATE_PROPERTY_EMBEDDED_TYPES in schema_payload["properties"][p]:
                _namespace_completion_categories(schema_payload, schema, p, TEMPLATE_PROPERTY_EMBEDDED_TYPES)

    with open(schema.absolute_path, "w") as target_file:
        target_file.write(json.dumps(schema_payload, indent=2))
