import os
import re
from typing import Dict

from openMINDS_pipeline.constants import NAMESPACE_PATTERNS
from openMINDS_pipeline.models import DirectoryStructure, OpenMINDSModule
from openMINDS_pipeline.utils import get_files_in_directory, load_json, detect_moved_files, save_file, version_key
from openMINDS_pipeline.vocab import enrich_types_with_identical
from openMINDS_pipeline.resolver import TEMPLATE_PROPERTY_TYPE


COMPILED_NAMESPACE_PATTERNS = {
    re.compile(pattern): replacement for pattern, replacement in NAMESPACE_PATTERNS.items()
}


def compare_versions(version1_dir: str, version2_dir: str, normalize: bool = True):
    """ Generate a changelog between two specific versions """
    files1 = get_files_in_directory(version1_dir)
    files2 = get_files_in_directory(version2_dir)
    version_name = os.path.basename(version2_dir)

    changelog = f"Release Notes {version_name}:\n"
    structured_changelog = {"title": f"Release Notes {version_name}"}

    # Track added and removed files
    added_files = sorted([file for file in set(files2) - set(files1) if file.endswith(".schema.omi.json")], key=lambda s: s.lower())
    removed_files = sorted([file for file in set(files1) - set(files2) if file.endswith(".schema.omi.json")], key=lambda s: s.lower())

    moved_files, moved_files_basename = detect_moved_files(added_files, removed_files)
    # Identify files to compare
    files_to_compare = sorted(set(files1).intersection(set(files2)), key=lambda s: s.lower())

    # Report global changes, checking the first file is enough
    _, _, _, global_changes = compare_files(version1_dir, version2_dir, files_to_compare[0],
                                                                         normalize)
    if "globalChanges" in global_changes:
        if global_changes["globalChanges"]:
            structured_changelog["globalChanges"] = global_changes["globalChanges"]
            changelog += f"\nGlobal changes:\n"
            changelog += f"  - " + "\n  - ".join(value for value in global_changes["globalChanges"]) + "\n"

    # Report added files
    if added_files:
        changelog += "\nAdded files:\n"
        structured_changelog["addedFiles"] = []
        for file in added_files:
            if os.path.basename(file) not in moved_files_basename:
                structured_changelog["addedFiles"].append(file)
                changelog += f"  - {file}\n"

    # Report removed files
    if removed_files:
        changelog += "\nRemoved files:\n"
        structured_changelog["removedFiles"] = []
        for file in removed_files:
            if os.path.basename(file) not in moved_files_basename:
                structured_changelog["removedFiles"].append(file)
                changelog += f"  - {file}\n"

    # Report moved files
    if moved_files:
        changelog += "\nMoved files:\n"
        structured_changelog["movedFiles"] = []
        for file in sorted(moved_files, key=lambda s: s.lower()):
            for removed_file in removed_files:
                if os.path.basename(file) == os.path.basename(removed_file):
                    structured_changelog["movedFiles"].append({"file":  os.path.basename(file), "source": removed_file, "destination": file})
                    changelog += f"  - {removed_file} moved to {file}\n"

    # Compare files for changes
    changes = []
    changed_types = {}
    for idx, file in enumerate(files_to_compare):
        diff, diff_structured, type_modified, global_changes = compare_files(version1_dir, version2_dir, file, normalize)
        if type_modified:
            changed_types[type_modified] = idx

        # Remove empty attributes from diff_structured
        diff_structured = {k: v for k, v in diff_structured.items() if v}

        if diff:
            changelog += f"\nChanges in {file}:\n"
            for change in diff:
                changelog += f"  - {change}\n"
        if diff_structured:
            changes.append({"file": file, **diff_structured})

    if changes:
        structured_changelog["changes"] = changes

    return changelog, structured_changelog, changed_types


def compare_files(version1_dir: str, version2_dir: str, filename: str, normalize: bool = True):
    """ Function to compare files between two versions """
    file1_path = os.path.join(version1_dir, filename)
    file2_path = os.path.join(version2_dir, filename)

    # Load the files
    schema1 = load_json(file1_path)
    schema2 = load_json(file2_path)

    if schema1 and schema2:
        return compare_json_schemas(schema1, schema2, normalize=normalize)
    else:
        return []


def compare_json_schemas(schema1, schema2, parent_key:str = "", normalize: bool = True):
    """ Recursively compare two schema files (comparison of the attributes) """
    changes = []
    type_modified = None
    structured_changes = {"addedAttributes": [], "removedAttributes": [], "modifiedAttributes": []}
    global_changes = {"globalChanges": []}

    def normalize_uri(uri, track_pattern: Dict = None):
        """ Helper function to normalize the prefixes """
        for pattern, replacement in NAMESPACE_PATTERNS.items():
            if re.match(pattern, uri):
                normalized_uri = re.sub(pattern, replacement, uri)
                if track_pattern is not None and uri != normalized_uri:
                    track_pattern[uri] = pattern
                return normalized_uri
        return uri

    # Normalize the URI if 'normalize' is True
    normalized_schema1 = {normalize_uri(key) if normalize else key: value for key, value in schema1.items()}
    normalized_schema2 = {normalize_uri(key) if normalize else key: value for key, value in schema2.items()}

    # Detect namespace change as global changes
    if normalize:
        namespaces_changes = set()
        for key1 in schema1:
            # Check if keys are the same in both schemas
            if key1 in schema2:
                # Handle keys "_type"
                if key1 == TEMPLATE_PROPERTY_TYPE and schema1[TEMPLATE_PROPERTY_TYPE] != schema2[TEMPLATE_PROPERTY_TYPE]:
                    patterns_dict1 = {}
                    patterns_dict2 = {}
                    normalize_uri(schema1[TEMPLATE_PROPERTY_TYPE], patterns_dict1)
                    normalize_uri(schema2[TEMPLATE_PROPERTY_TYPE], patterns_dict2)
                    pattern1 = next(iter(patterns_dict1.values()), None)
                    pattern2 = next(iter(patterns_dict2.values()), None)
                    # Ignore '_type" renaming
                    if pattern1 != pattern2:
                        namespaces_changes.add(f"Namespace changed from {pattern1} to {pattern2}.")
                continue

            # Check if keys are the same in both schemas after normalization
            patterns_dict1 = {}
            normalized_key1 = normalize_uri(key1, patterns_dict1)
            for key2 in schema2:
                patterns_dict2 = {}
                normalized_key2 = normalize_uri(key2, patterns_dict2)
                if normalized_key1 == normalized_key2:
                    namespaces_changes.add(f"Namespace changed from {patterns_dict1[key1]} to {patterns_dict2[key2]}.")
                    break

        if namespaces_changes:
            global_changes["globalChanges"].extend(namespaces_changes)

    # Find keys present in schema1 but not in schema2
    for key in sorted(normalized_schema1, key=lambda s: s.lower()):
        if key not in normalized_schema2:
            changes.append(f"Field '{parent_key + key}' removed.")
            structured_changes["removedAttributes"].append(parent_key + key)

    # Find keys present in schema2 but not in schema1
    for key in sorted(normalized_schema2, key=lambda s: s.lower()):
        if key not in normalized_schema1:
            changes.append(f"Field '{parent_key + key}' added.")
            structured_changes["addedAttributes"].append(parent_key + key)

    # Check for modified properties or nested dictionaries
    for key in sorted(normalized_schema1, key=lambda s: s.lower()):
        if key in normalized_schema2:
            # If the values are dictionaries, we need to compare them recursively
            if isinstance(normalized_schema1[key], dict) and isinstance(normalized_schema2[key], dict):
                nested_changes, nested_structured_changes, _, nested_global_changes = compare_json_schemas(normalized_schema1[key], normalized_schema2[key], parent_key + key + ".", normalize)
                if nested_global_changes:
                    global_changes["globalChanges"].extend(nested_global_changes["globalChanges"])
                changes.extend(nested_changes)
                for category, value in nested_structured_changes.items():
                    if category != "schemaType":
                        structured_changes[category].extend(value)
            # Otherwise, compare the values directly
            elif normalized_schema1[key] != normalized_schema2[key]:
                # Ignore if both values represent the same resource after replacement of the namespace
                if isinstance(normalized_schema1[key], str) and isinstance(normalized_schema2[key], str) and normalize_uri(normalized_schema1[key]) == normalize_uri(normalized_schema2[key]):
                    pass
                elif (normalize1 := [normalize_uri(value1) for value1 in normalized_schema1[key]]) != (normalize2 :=[normalize_uri(value2) for
                                                                                           value2 in
                                                                                           normalized_schema2[key]]):
                    if type(normalized_schema1[key]) is list and type(normalized_schema2[key]) is list and len(normalize2) > len(normalize1) and set(normalize1).issubset(set(normalize2)):
                        changes.append(f"Field '{parent_key + key}' modified (value(s) added).")
                        structured_changes["modifiedAttributes"].append({'property':parent_key + key, 'modification': 'value(s) added'})
                    elif type(normalized_schema1[key]) is list and type(normalized_schema2[key]) is list and len(normalize1) > len(normalize2) and set(normalize2).issubset(set(normalize1)):
                        changes.append(f"Field '{parent_key + key}' modified (value(s) removed).")
                        structured_changes["modifiedAttributes"].append({'property':parent_key + key, 'modification': 'value(s) removed'})
                    else:
                        changes.append(f"Field '{parent_key + key}' modified.")
                        structured_changes["modifiedAttributes"].append({'property': parent_key + key})

    if changes and "schemaType" not in structured_changes:
        if "name" in normalized_schema1 and "name" in normalized_schema1:
            if normalized_schema1["name"] == normalized_schema2["name"]:
                structured_changes["schemaType"] = normalized_schema1["name"]
                type_modified = structured_changes["schemaType"]

    return changes, structured_changes, type_modified, global_changes


def generate_changelogs_and_compatibility_resolution(versions: Dict[str, Dict[str, OpenMINDSModule]], directory_structure: DirectoryStructure):
    """
    Compare schema versions, generate changelogs, and enrich vocab types.
    """
    versions = sorted(list(versions.keys()), key=version_key)
    target_directory = directory_structure.target_directory
    vocab_types = load_json(os.path.join(target_directory, 'vocab', 'types.json'))

    for i in range(1, len(versions)):
        current_version = versions[i]
        previous_version = versions[i - 1]

        print(f"Now building the changelog for {current_version}.")
        schemas_previous_version = os.path.join(target_directory, 'schemas', previous_version)
        schemas_current_version = os.path.join(target_directory, 'schemas', current_version)
        changelog_content, structured_changelog_content, changed_types = compare_versions(
            schemas_previous_version,
            schemas_current_version,
            normalize=True
        )

        # Save changelogs in txt and JSON formats
        changelog_dir = os.path.join(target_directory, 'schemas', current_version)
        os.makedirs(changelog_dir, exist_ok=True)
        save_file(os.path.join(changelog_dir, f"release_notes_{current_version}.txt"), changelog_content)
        save_file(os.path.join(changelog_dir, f"release_notes_{current_version}.json"),
                  structured_changelog_content, is_json=True)

        enrich_types_with_identical(vocab_types, changed_types, previous_version, current_version, i)

    save_file(os.path.join(target_directory, 'vocab', 'types.json'), vocab_types, is_json=True, sort_keys=True)
