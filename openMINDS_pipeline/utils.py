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

from openMINDS_pipeline.constants import SCHEMA_FILE_ENDING
from openMINDS_pipeline.models import Trigger, OpenMINDSModule, DirectoryStructure, SchemaStructure
from openMINDS_pipeline.resolver import TEMPLATE_PROPERTY_TYPE


def clone_sources(modules, version):
    if os.path.exists("sources"):
        shutil.rmtree("sources")
    print(f"Now building the version {version}")
    for module, spec in modules.items():
        print(f"Cloning module {module} in commit {spec.commit}")
        repo = Repo.clone_from(spec.repository, f"sources/{module}", no_checkout=True)
        repo.git.checkout(spec.commit)
    print("Done cloning")


def evaluate_versions_to_be_built(trigger:Optional[Trigger]) -> Dict[str, Dict[str, OpenMINDSModule]]:
    """
    :return: the dictionary describing all versions supposed to be built either because of a change or because of a build of everything.
    """
    if trigger:
        print(f"Triggered by a submodule change of module {trigger.repository} in version {trigger.branch}")
    else:
        print("No specific trigger - going to build everything...")
    if os.path.exists("central"):
        shutil.rmtree("central")
    repo = Repo.clone_from("https://github.com/openMetadataInitiative/openMINDS.git", "central", depth=1)
    repo.git.checkout("main")
    with open("central/versions.json", "r") as version_specs:
        versions = json.load(version_specs)
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
        if not trigger or (is_dynamic and triggering_module.branch and triggering_module.branch == trigger.branch):
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
        absolute_schema_group_src_dir = directory_structure.evaluate_absolute_schema_dir(schema_group)
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

