SCHEMA_FILE_ENDING = ".schema.tpl.json"
INSTANCE_FILE_ENDING = ".jsonld"
FIRST_VERSION = "v1.0"
# Replacement mappings
NAMESPACE_PATTERNS = {
    r"https://openminds.ebrains.eu/vocab/": "props:",
    r"https://openminds.ebrains.eu/(?!vocab/)[^/]+/": "types:",
    r"https://openminds.om-i.org/props/": "props:",
    r"https://openminds.om-i.org/types/": "types:"
}
