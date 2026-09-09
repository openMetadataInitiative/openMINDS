SCHEMA_FILE_ENDING = ".schema.tpl.json"
INSTANCE_FILE_ENDING = ".jsonld"
FIRST_VERSION = "v1.0"
# Files in a "schemas" directory which do not end in SCHEMA_FILE_ENDING but are tolerated anyway.
# This prevents new types being added to old releases.
# Do not add an entry here for a version whose content can still be corrected: just fix the file name.
KNOWN_UNMATCHED_SCHEMA_FILES = {
    ("v3.0", "core", "schemas/digitalIdentifier/genericIdentifier.tpl.json"),
    ("v4.0", "core", "schemas/digitalIdentifier/genericIdentifier.tpl.json")
}
# Replacement mappings
NAMESPACE_PATTERNS = {
    r"https://openminds.ebrains.eu/vocab/": "props:",
    r"https://openminds.ebrains.eu/(core|sands|controlledTerms|chemicals|ephys|computation|stimulation|specimenPrep|publications|neuroimaging)/": "types:",
    r"https://openminds.om-i.org/props/": "props:",
    r"https://openminds.om-i.org/types/": "types:"
}
