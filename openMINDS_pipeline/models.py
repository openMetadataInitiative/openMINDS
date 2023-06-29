import glob
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional, List

from openMINDS_pipeline.constants import SCHEMA_FILE_ENDING


@dataclass
class OpenMINDSModule:
    repository: str
    branch: Optional[str] = field(default=None)
    commit: Optional[str] = field(default=None)


@dataclass
class Trigger:
    branch: str
    repository: str


class SchemaStructure:
    def __init__(self, type, schema_group, version, file):
        self.type = type
        self.schema_group = schema_group
        self.file = file
        self.version = version
        self.categories = None
        self.absolute_path = None

    def set_categories(self, categories):
        self.categories = categories

    def set_absolute_path(self, absolute_path):
        self.absolute_path = absolute_path

    def get_relative_path_for_expanded(self):
        return f"{self.schema_group}/{self.version}/{self.file}"

    def get_schema_name(self):
        return self.get_relative_path_for_expanded()[0:-len(SCHEMA_FILE_ENDING)]


class DirectoryStructure:

    def __init__(self):
        self._root_directory = os.path.realpath(".")
        self.source_directory = os.path.join(self._root_directory, "sources")
        self.central_directory = os.path.join(self._root_directory, "central")
        self.expanded_directory = os.path.join(self._root_directory, "expanded")
        self.target_directory = os.path.join(self._root_directory, "target")
        pass

    @staticmethod
    def clear_directory(directory):
        if os.path.exists(directory):
            print(f"clearing directory {directory}")
            shutil.rmtree(directory)

    def is_part_of_working_directory(self, directory) -> bool:
        return directory.startswith(self.source_directory) and os.path.isfile(directory)

    def source_schema_directory(self, schema_group:str) -> str:
        return os.path.join(self.source_directory, schema_group, "schemas")

    def expanded_schema_directory(self, schema: SchemaStructure) -> str:
        return os.path.join(self.expanded_directory, schema.schema_group)

    def find_resource_directories(self, file_ending) -> List[str]:
        """
        Finds directories of the files with the given file ending in the given working directory
        :param file_ending:
        :return:
        """
        resource_directories = set()
        for source in glob.glob(os.path.join(self.source_directory, f'**/*{file_ending}'), recursive=True):
            resource_dir = os.path.dirname(source)[len(self.source_directory) + 1:]
            if ("target" not in resource_dir and "expanded" not in resource_dir):
                path_split = resource_dir.split("/")
                if len(path_split) == 1:
                    resource_directories.add(path_split[0])
                else:
                    resource_directories.add("/".join([path_split[0], path_split[1]]))
        return list(resource_directories)

