import glob
import os
import json
import re
import shutil
from json import JSONDecodeError
from typing import Optional, Dict, List

from git import Repo, Git
from packaging.utils import canonicalize_version
from packaging.version import Version

from openMINDS_pipeline.constants import SCHEMA_FILE_ENDING, OPENMINDS_VOCAB
from openMINDS_pipeline.models import Trigger, OpenMINDSModule, DirectoryStructure, SchemaStructure
from openMINDS_pipeline.resolver import TEMPLATE_PROPERTY_TYPE


def clone_central(refetch:bool):
    if refetch and os.path.exists("target"):
        shutil.rmtree("target")
    if not os.path.exists("target"):
        Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", "target")
        shutil.rmtree("target/.git")


def clone_sources(modules, version):
    print(f"Now building the version {version}")
    for module, spec in modules.items():
        print(f"Cloning module {module} in commit {spec.commit}")
        repo = Repo.clone_from(spec.repository, f"sources/{module}", no_checkout=True)
        repo.git.checkout(spec.commit)
    print("Done cloning")


def is_edge(property_definition:dict):
    embedded_types = property_definition["_embeddedTypes"] if "_embeddedTypes" in property_definition else None
    linked_types = property_definition["_linkedTypes"] if "_linkedTypes" in property_definition else None
    return embedded_types, linked_types, bool(embedded_types or linked_types)


def get_basic_type(property_definition:dict) -> Optional[str]:
    basic_type = None
    if "type" in property_definition:
        basic_type = property_definition["type"]
        if basic_type == "array" and "items" in property_definition and "type" in property_definition["items"]:
            basic_type = property_definition["items"]["type"]
    return basic_type


def evaluate_versions_to_be_built(version_config: str, trigger:Optional[Trigger]) -> Dict[str, Dict[str, OpenMINDSModule]]:
    """
    :return: the dictionary describing all versions supposed to be built either because of a change or because of a build of everything.
    """
    if trigger:
        print(f"Triggered by a submodule change of module {trigger.repository} in version {trigger.branch}")
    else:
        print("No specific trigger - going to build everything...")
    if os.path.exists("pipeline"):
        shutil.rmtree("pipeline")
    repo = Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", "pipeline")
    repo.git.checkout("pipeline")

    with open(os.path.join("pipeline", version_config), "r") as version_specs:
        versions = json.load(version_specs)
    if os.path.exists("pipeline"):
        shutil.rmtree("pipeline")
    relevant_versions = {}
    for version, modules in versions.items():
        triggering_module = None
        is_dynamic = False
        new_modules = {}
        for module, module_spec in modules.items():
            m = OpenMINDSModule(**module_spec)
            if not m.branch:
                is_dynamic = True
                _evaluate_branch_and_commit_for_dynamic_instances(m)
            if trigger and m.repository and m.repository.endswith(f"{trigger.repository}.git"):
                triggering_module = m
            new_modules[module] = m
        # The version is only relevant if the process was not launched by a submodule change (so everything is built) or if the triggering module is specified with the given branch
        if not trigger or (is_dynamic and triggering_module and triggering_module.branch and triggering_module.branch == trigger.branch):
            relevant_versions[version] = new_modules
    return relevant_versions


def _evaluate_branch_and_commit_for_dynamic_instances(module_spec:OpenMINDSModule):
    git_instance = Git()
    branches = git_instance.ls_remote('--heads', module_spec.repository).splitlines()
    semantic_to_branchname = {}
    branch_to_commit = {y[1]: y[0] for y in [x.split("\trefs/heads/") for x in branches] if re.match("v[0-9]+.*", y[1])}
    for branch_name in list(branch_to_commit.keys()):
        semantic = canonicalize_version(branch_name)
        semantic = f"{semantic}.0" if "." not in semantic else semantic
        semantic_to_branchname[semantic] = branch_name
    version_numbers = list(semantic_to_branchname.keys())
    version_numbers.sort(key=Version, reverse=True)
    latest_branch_name = semantic_to_branchname[version_numbers[0]]
    module_spec.branch = latest_branch_name
    module_spec.commit = branch_to_commit[latest_branch_name]


def find_schemas(directory_structure: DirectoryStructure, modules: Dict[str, OpenMINDSModule]) -> List[SchemaStructure]:
    schema_information = []
    for schema_group in directory_structure.find_resource_directories(file_ending=SCHEMA_FILE_ENDING):
        schema_group = schema_group.split("/")[0]
        version = modules[schema_group].branch
        absolute_schema_group_src_dir = directory_structure.source_schema_directory(schema_group)
        if os.path.isdir(absolute_schema_group_src_dir):
            print(f"handling schemas of {schema_group}")
            for schema_path in glob.glob(os.path.join(absolute_schema_group_src_dir, f'**/*{SCHEMA_FILE_ENDING}'), recursive=True):
                relative_schema_path = schema_path[len(absolute_schema_group_src_dir) + 1:]
                try:
                    with open(schema_path, "r") as schema_file:
                        schema = json.load(schema_file)
                    if TEMPLATE_PROPERTY_TYPE in schema:
                        schema_information.append(SchemaStructure(schema[TEMPLATE_PROPERTY_TYPE], schema_group, version, relative_schema_path))
                    else:
                        print(f"Skipping schema {relative_schema_path} because it doesn't contain a valid type")
                except JSONDecodeError:
                    print(f"Skipping schema {relative_schema_path} because it is not a valid JSON document")
        else:
            print(f"Skipping schemas of {schema_group} since there is no schemas directory")
    return schema_information


def qualify_property_names(schemas:List[SchemaStructure]):
    for schema in schemas:
        with open(schema.absolute_path, "r") as schema_file:
            schema_payload = json.load(schema_file)
        if "properties" in schema_payload:
            new_properties = {}
            for p, v in schema_payload["properties"].items():
                new_properties[f"{OPENMINDS_VOCAB}{p}"] = v
            schema_payload["properties"] = new_properties
        if "required" in schema_payload:
            schema_payload["required"] = [f"{OPENMINDS_VOCAB}{p}" for p in schema_payload["required"]]
            schema_payload["required"].sort()

        with open(schema.absolute_path, "w") as target_file:
            target_file.write(json.dumps(schema_payload, indent=2, sort_keys=True))


def copy_to_target_directory(directory_structure: DirectoryStructure, version:str):
    schemas_version_directory = os.path.join(directory_structure.target_directory, "schemas", version)
    if os.path.exists(schemas_version_directory):
        shutil.rmtree(schemas_version_directory)
    shutil.copytree(directory_structure.expanded_directory, schemas_version_directory)
    for root, dirs, files in os.walk(schemas_version_directory):
        for file_name in files:
            new_file_name = file_name.replace(".schema.tpl.json", ".schema.omi.json")
            os.rename(os.path.join(root, file_name), os.path.join(root, new_file_name))
