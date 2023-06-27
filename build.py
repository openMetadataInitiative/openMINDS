import argparse

import sys

from openMINDS_pipeline.models import DirectoryStructure, Trigger
from openMINDS_pipeline.resolver import DependencyResolver
from openMINDS_pipeline.utils import clone_sources, find_schemas, evaluate_versions_to_be_built

parser = argparse.ArgumentParser(prog=sys.argv[0], description='Expand openMINDS schema, extract vocabularies and instances')
parser.add_argument('--branch', help="The branch that triggered the re-build", default=None)
parser.add_argument('--repository', help="The repository that triggered the re-build", default=None)
args = vars(parser.parse_args())
trigger = Trigger(args["branch"] if args["branch"] != "" else None, args["repository"] if args["repository"] != "" else None) if args["branch"] and args["repository"] else None

print("***************************************")
print(f"Triggering the generation of sources for openMINDS")
print("***************************************")

directory_structure = DirectoryStructure("sources")

# Step 1 - find the versions to be (re-)built
relevant_versions = evaluate_versions_to_be_built(trigger)

for version, modules in relevant_versions.items():

    directory_structure.clear_target_directory()

    # Step 2 - Clone all required resources for the aggregation
    clone_sources(modules, version)

    # Step 3 - Find all involved schemas
    all_schemas = find_schemas(directory_structure, modules)

    # Step 4 - Resolve all "_extends" directives and save to target directory
    DependencyResolver.resolve_extends(all_schemas, directory_structure)

    # Step 5 - Resolve all categories to type lists in target directory
    DependencyResolver.resolve_categories(all_schemas)

    # # Step 6 - Extract vocabulary from sources
    # types_file, properties_file = VocabExtractor(all_schemas, args["path"], args["reinit"], args["current"], args["vocab"]).extract()
    #
    # # Step 7 - Enrich the schemas with vocab information
    # VocabEnrichment.enrich_with_vocab(types_file, properties_file, all_schemas, )

