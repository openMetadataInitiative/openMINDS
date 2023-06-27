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
    EXPANDED_DIR = "expanded"

    def __init__(self, working_directory):
        self._working_directory = os.path.realpath(working_directory)
        self._target_directory = self._evaluate_absolute_target_dir()
        pass

    def clear_target_directory(self):
        if os.path.exists(self._target_directory):
            print("clearing previously generated expanded sources")
            shutil.rmtree(self._target_directory)

    @staticmethod
    def _evaluate_absolute_target_dir():
        return os.path.realpath(os.path.join(os.path.realpath("."), DirectoryStructure.EXPANDED_DIR))

    def is_part_of_working_directory(self, directory) -> bool:
        return directory.startswith(self._working_directory) and os.path.isfile(directory)

    def evaluate_absolute_schema_dir_for_schema_path(self, schema_path: str) -> str:
        return os.path.join(self._working_directory, schema_path)

    def evaluate_absolute_schema_dir(self, schema_group:str) -> str:
        return os.path.join(self._working_directory, schema_group, "schemas")

    def evaluate_absolute_schema_target_directory(self, schema: SchemaStructure) -> str:
        return os.path.realpath(os.path.join(self._target_directory, schema.schema_group, schema.version))

    def find_resource_directories(self, file_ending) -> List[str]:
        """
        Finds directories of the files with the given file ending in the given working directory
        :param file_ending:
        :return:
        """
        resource_directories = set()
        for source in glob.glob(os.path.join(self._working_directory, f'**/*{file_ending}'), recursive=True):
            resource_dir = os.path.dirname(source)[len(self._working_directory) + 1:]
            if ("target" not in resource_dir
                    and DirectoryStructure.EXPANDED_DIR not in resource_dir
            ):
                path_split = resource_dir.split("/")
                if len(path_split) == 1:
                    resource_directories.add(path_split[0])
                else:
                    resource_directories.add("/".join([path_split[0], path_split[1]]))
        return list(resource_directories)

