SCHEMA_FILE_ENDING = ".schema.tpl.json"
INSTANCE_FILE_ENDING = ".jsonld"
# Replacement mappings
namespace_replacement_patterns = {
    r"https://openminds.ebrains.eu/vocab/": "props:",
    r"https://openminds.ebrains.eu/(?!vocab/)[^/]+/": "types:",
    r"https://openminds.om-i.org/props/": "props:",
    r"https://openminds.om-i.org/types/": "types:"
}
