import abc
import contextlib
import json
import os

from pathlib import Path

import yaml

from ..config import settings


def get_directories(path: Path) -> list[str]:
    """Returns a list of directories in a given path."""
    directories = []
    for entry_path in path.iterdir():
        if entry_path.is_dir():
            directories.append(entry_path.name)
    return directories


class AbstractFilesystem(abc.ABC):
    def __init__(self, root: Path):
        self.root = root

    @abc.abstractmethod
    def list(self) -> list[str]:
        """Returns a list of directories for a given root."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_config_by_name(self, name: str) -> dict:
        """Returns a dictionary containing the configuration for a given service name."""
        raise NotImplementedError


class Filesystem(AbstractFilesystem):
    def list(self):
        directories = []
        for entry_path in self.root.iterdir():
            if entry_path.is_dir():
                directories.append(entry_path.name)
        return directories

    def get_config_by_name(self, name):
        config_path = self.root / name / "config.json"
        data_dict = {}
        with config_path.open() as config_file:
            data_dict = json.load(config_file)
        if not isinstance(data_dict, dict):
            raise TypeError("config is not a dict")
        # if ansible_playbook is set, read steps directly from playbook
        if "ansible_playbook" in data_dict:
            data_dict["steps"] = get_steps_from_playbook(data_dict["ansible_playbook"])
        return data_dict


@contextlib.contextmanager
def working_directory(path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev_cwd)


def get_steps_from_playbook(path_from_config: str) -> list[dict]:
    """
    Avoid mismatch between list of steps and ansible by getting
    the steps directly from the playbook.
    """
    playbook_path = settings.project_root / path_from_config
    with playbook_path.open("r") as playbook_file:
        parsed = yaml.safe_load(playbook_file)
    steps = []
    if "tasks" in parsed[0]:
        # workaround for ansible-galaxy (just roles, no tasks)
        steps = [{"name": task["name"]} for task in parsed[0]["tasks"] if "name" in task]
        steps.insert(0, {"name": "Gathering Facts"})
    return steps
