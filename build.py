import argparse
import sys

from openMINDS_pipeline.models import DirectoryStructure, Trigger
from openMINDS_pipeline.resolver import resolve_extends, resolve_categories
from openMINDS_pipeline.utils import clone_sources, find_schemas, evaluate_versions_to_be_built, clone_central, qualify_property_names, copy_to_target_directory
from openMINDS_pipeline.vocab import TypeExtractor, Types, PropertyExtractor, Property, enrich_with_types_and_properties

parser = argparse.ArgumentParser(prog=sys.argv[0], description='Expand openMINDS schema, extract vocabularies and instances')
parser.add_argument('--branch', help="The branch that triggered the re-build", default=None)
parser.add_argument('--repository', help="The repository that triggered the re-build", default=None)
parser.add_argument('--config', help="Version configuration file", default="versions.json")
args = vars(parser.parse_args())
trigger = Trigger(args["branch"] if args["branch"] != "" else None, args["repository"] if args["repository"] != "" else None) if args["branch"] and args["repository"] else None

print("***************************************")
print(f"Triggering the generation of sources for openMINDS")
print("***************************************")

directory_structure = DirectoryStructure()
clone_central(True)

# Step 1 - find the versions to be (re-)built
relevant_versions, namespaces = evaluate_versions_to_be_built(args["config"], trigger)

for version, modules in relevant_versions.items():
    DirectoryStructure.clear_directory(directory_structure.expanded_directory)
    DirectoryStructure.clear_directory(directory_structure.source_directory)

    # Step 2 - Clone all required resources for the aggregation
    clone_sources(modules, version)

    # Step 3 - Find all involved schemas
    all_schemas = find_schemas(directory_structure, modules, namespaces[version])

    # Step 4 - Resolve all "_extends" directives and save to target directory
    resolve_extends(all_schemas, directory_structure)

    # Step 5 - Resolve all categories to type lists in target directory. Also saves an overview of categories to type mapping by version into categories.json
    resolve_categories(version, directory_structure, all_schemas)

    # Step 6 - Qualify the properties of the schemas
    qualify_property_names(all_schemas)

    # Step 7 - Extract types from sources and update types.json
    extracted_types = TypeExtractor(directory_structure, version).extract_types(all_schemas)

    # Step 8- Extract properties from source and update properties.json
    extracted_properties = PropertyExtractor(directory_structure, version).extract_properties(all_schemas)

    # Step 9 - Enrich the schemas with central types and properties information
    enrich_with_types_and_properties(version, extracted_types, extracted_properties, all_schemas)

    # Step 10 - Copy results to the target directory
    copy_to_target_directory(directory_structure, version)

if not trigger:
    # We've built everything - this is the only chance to do a proper cleanup at the end because we know all versions have been processed.
    Types(directory_structure).clean_types()
    Property(directory_structure).clean_properties()
