import os
import json
import re

from openMINDS_pipeline.constants import namespace_replacement_patterns
from openMINDS_pipeline.utils import get_files_in_directory, load_json, detect_moved_files


def generate_version_comparison(version1_dir, version2_dir):
    """ Generate a changelog between two specific versions """
    files1 = get_files_in_directory(version1_dir)
    files2 = get_files_in_directory(version2_dir)

    changelog = f"Release Notes {os.path.basename(version2_dir)}:\n"

    # Track added and removed files
    added_files = sorted([file for file in set(files2) - set(files1) if file.endswith(".schema.omi.json")], key=lambda s: s.lower())
    removed_files = sorted([file for file in set(files1) - set(files2) if file.endswith(".schema.omi.json")], key=lambda s: s.lower())

    moved_files, moved_files_basename = detect_moved_files(added_files, removed_files)

    # Report added files
    if added_files:
        changelog += "\nAdded files:\n"
        for file in added_files:
            if os.path.basename(file) not in moved_files_basename:
                changelog += f"  - {file}\n"

    # Report removed files
    if removed_files:
        changelog += "\nRemoved files:\n"
        for file in removed_files:
            if os.path.basename(file) not in moved_files_basename:
                changelog += f"  - {file}\n"

    # Report moved files
    if moved_files:
        changelog += "\nMoved files:\n"
        for file in sorted(moved_files, key=lambda s: s.lower()):
            for removed_file in removed_files:
                if os.path.basename(file) == os.path.basename(removed_file):
                    changelog += f"  - {removed_file} moved to {file}\n"

    # Identify files to compare
    files_to_compare = sorted(set(files1).intersection(set(files2)), key=lambda s: s.lower())

    # Compare files for changes
    for file in files_to_compare:
        diff = compare_files(version1_dir, version2_dir, file)
        if diff:
            changelog += f"\nChanges in {file}:\n"
            for change in diff:
                changelog += f"  - {change}\n"

    return changelog


def compare_files(version1_dir, version2_dir, filename):
    """ Function to compare files between two versions """
    file1_path = os.path.join(version1_dir, filename)
    file2_path = os.path.join(version2_dir, filename)

    # Load the files
    schema1 = load_json(file1_path)
    schema2 = load_json(file2_path)

    if schema1 and schema2:
        return compare_json_schemas(schema1, schema2)
    else:
        return []


def compare_json_schemas(schema1, schema2, parent_key=""):
    """ Recursively compare two schema files (comparison of the attributes) """
    changes = []

    # Compile a single regex pattern that matches any URI
    pattern = re.compile("|".join(re.escape(uri) for uri in namespace_replacement_patterns))

    def normalize_uri(uri):
        """ Helper function to normalize the prefixes """
        # Return the original value if no replacement was applied
        return next(
            (re.sub(pattern, replacement, uri) for pattern, replacement in namespace_replacement_patterns.items() if
             re.match(pattern, uri)), uri)

    normalized_schema1 = {normalize_uri(key): value for key, value in schema1.items()}
    normalized_schema2 = {normalize_uri(key): value for key, value in schema2.items()}

    # Find keys present in schema1 but not in schema2
    for key in sorted(normalized_schema1, key=lambda s: s.lower()):
        if key not in normalized_schema2:
            changes.append(f"Field '{parent_key + key}' removed.")

    # Find keys present in schema2 but not in schema1
    for key in sorted(normalized_schema2, key=lambda s: s.lower()):
        if key not in normalized_schema1:
            changes.append(f"Field '{parent_key + key}' added.")

    # Check for modified properties or nested dictionaries
    for key in sorted(normalized_schema1, key=lambda s: s.lower()):
        if key in normalized_schema2:
            # If the values are dictionaries, we need to compare them recursively
            if isinstance(normalized_schema1[key], dict) and isinstance(normalized_schema2[key], dict):
                nested_changes = compare_json_schemas(normalized_schema1[key], normalized_schema2[key], parent_key + key + ".")
                changes.extend(nested_changes)
            # Otherwise, compare the values directly
            elif normalized_schema1[key] != normalized_schema2[key]:
                # Ignore if both values represent the same resource after replacement of the namespace
                if isinstance(normalized_schema1[key], str) and isinstance(normalized_schema2[key], str) and normalize_uri(normalized_schema1[key]) == normalize_uri(normalized_schema2[key]):
                    pass
                elif [normalize_uri(value1) for value1 in normalized_schema1[key]] != [normalize_uri(value2) for value2 in normalized_schema2[key]]:
                    changes.append(f"Field '{parent_key + key}' modified.")

    return changes
