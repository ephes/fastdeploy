import abc
import contextlib
import json
import os
import stat
from pathlib import Path

import yaml

from ..config import settings


class AbstractFilesystem(abc.ABC):
    def __init__(self, root: Path):
        self.root = root

    @abc.abstractmethod
    def list(self) -> list[str]:
        """Returns a list of directories for a given root."""
        raise NotImplementedError  # pragma: no cover

    @abc.abstractmethod
    def get_config_by_name(self, name: str) -> dict:
        """Returns a dictionary containing the configuration for a given service name."""
        raise NotImplementedError  # pragma: no cover


MAX_CONFIG_BYTES = 1024 * 1024
MAX_CONFIG_DEPTH = 32
MAX_CONFIG_NODES = 50000


class ServiceConfigError(ValueError):
    """A bounded, value-free service configuration admission failure."""


def _relative_parts(path: Path) -> tuple[str, ...]:
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ServiceConfigError("service config path is outside approved roots")
    return path.parts


def _read_regular(root: Path, relative: Path) -> str:
    """Walk below an operator-selected root using pinned no-follow descriptors."""
    parts = _relative_parts(relative)
    try:
        with contextlib.ExitStack() as stack:
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, directory)
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                stack.callback(os.close, directory)
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            stack.callback(os.close, descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
                raise ServiceConfigError("service config must be a regular file of at most 1 MiB")
            # The duplicate keeps ExitStack responsible for the original handle.
            with os.fdopen(os.dup(descriptor), "rb") as source:
                content = source.read(MAX_CONFIG_BYTES + 1)
            if len(content) > MAX_CONFIG_BYTES:
                raise ServiceConfigError("service config exceeds 1 MiB")
            return content.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ServiceConfigError):
            raise
        raise ServiceConfigError("service config file is unavailable or invalid") from None


def _check_structure(value):
    # Iterative traversal also bounds recursive/shared YAML aliases.
    pending = [(value, 1)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > MAX_CONFIG_DEPTH or visited > MAX_CONFIG_NODES:
            raise ServiceConfigError("service config exceeds depth or node limit")
        children = list(item.values()) if isinstance(item, dict) else item if isinstance(item, list) else ()
        if len(pending) + len(children) + visited > MAX_CONFIG_NODES:
            raise ServiceConfigError("service config exceeds node limit")
        pending.extend((child, depth + 1) for child in children)


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        try:
            if key in result:
                raise ServiceConfigError("service config contains duplicate mapping keys")
            result[key] = value
        except TypeError:
            raise ServiceConfigError("service config contains an invalid mapping key") from None
    return result


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def _check_mapping_keys(self, node):
        # Aliases share nodes; check each node once so merge chains of aliases stay linear.
        checked = self.__dict__.setdefault("_checked_mapping_nodes", set())
        if id(node) in checked:
            return
        checked.add(id(node))
        # Check the keys written in this mapping before flattening removes merge keys. Keys
        # merged in with "<<" follow the YAML merge rules: explicit keys override merged
        # ones and earlier merge sources win over later ones. Merge sources are flattened,
        # not constructed, so check their own keys here as well.
        merges = 0
        explicit = []
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:value":
                key_node.tag = "tag:yaml.org,2002:str"  # as flatten_mapping does for a bare "="
            if key_node.tag != "tag:yaml.org,2002:merge":
                explicit.append((self.construct_object(key_node, deep=True), None))
                continue
            merges += 1
            sources = value_node.value if isinstance(value_node, yaml.SequenceNode) else [value_node]
            for source in sources:
                if isinstance(source, yaml.MappingNode):
                    self._check_mapping_keys(source)
        if merges > 1:
            raise ServiceConfigError("service config contains duplicate mapping keys")
        _unique_mapping(explicit)

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            self._check_mapping_keys(node)
        return super().construct_mapping(node, deep=deep)


def _load_document(content: str, *, playbook=False):
    try:
        if playbook:
            depth = 0
            for count, event in enumerate(yaml.parse(content), 1):
                if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                    depth += 1
                elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                    depth -= 1
                if depth > MAX_CONFIG_DEPTH or count > MAX_CONFIG_NODES:
                    raise ServiceConfigError("playbook exceeds depth or node limit")
            value = yaml.load(content, Loader=_UniqueKeySafeLoader)
        else:
            value = json.loads(content, object_pairs_hook=_unique_mapping)
        _check_structure(value)
        return value
    except (ValueError, RecursionError, yaml.YAMLError):
        raise ServiceConfigError("service config has invalid syntax, depth or structure") from None


def _validate_service_definition(data):
    if "deploy_script" in data:
        script = data["deploy_script"]
        if not isinstance(script, str) or not script.strip() or "\x00" in script:
            raise ServiceConfigError("deploy_script must be a nonempty executable path")
    if "steps" in data:
        steps = data["steps"]
        if not isinstance(steps, list) or not all(
            isinstance(step, dict)
            and isinstance(step.get("name"), str)
            and 0 < len(step["name"]) <= 255
            and step["name"].strip()
            and "\x00" not in step["name"]
            for step in steps
        ):
            raise ServiceConfigError("steps must be a list of objects with nonblank names of at most 255 characters")


class Filesystem(AbstractFilesystem):
    def list(self):
        """Refuse aliases rather than silently dropping a service during sync."""
        directories = []
        try:
            for entry_path in self.root.iterdir():
                mode = entry_path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    raise ServiceConfigError("service directory aliases are not supported")
                if stat.S_ISDIR(mode):
                    directories.append(entry_path.name)
        except OSError:
            raise ServiceConfigError("service configuration root is unavailable") from None
        return directories

    def get_config_by_name(self, name):
        if not isinstance(name, str) or len(Path(name).parts) != 1 or name in (".", ".."):
            raise ServiceConfigError("invalid service directory name")
        data_dict = _load_document(_read_regular(self.root, Path(name) / "config.json"))
        if not isinstance(data_dict, dict):
            raise ServiceConfigError("service config must be an object")
        _validate_service_definition(data_dict)
        if "ansible_playbook" in data_dict:
            data_dict["steps"] = get_steps_from_playbook(data_dict["ansible_playbook"], config_root=self.root)
        _validate_service_definition(data_dict)
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


def get_steps_from_playbook(path_from_config: str, *, config_root: Path | None = None) -> list[dict]:
    """Read an admitted playbook below the project/config or approved extra roots."""
    if not isinstance(path_from_config, str) or not path_from_config or "\x00" in path_from_config:
        raise ServiceConfigError("invalid playbook path")
    path = Path(path_from_config)
    if ".." in path.parts:
        raise ServiceConfigError("playbook parent traversal is not supported")
    roots = [settings.project_root, *settings.service_playbook_roots]
    if config_root is not None:
        roots.append(config_root)
    if not path.is_absolute():
        content = _read_regular(settings.project_root, path)
    else:
        for root in roots:
            root = root.absolute()
            if path.is_relative_to(root):
                content = _read_regular(root, path.relative_to(root))
                break
        else:
            raise ServiceConfigError("playbook path is outside approved roots")
    parsed = _load_document(content, playbook=True)
    if not isinstance(parsed, list) or not parsed or not all(isinstance(play, dict) for play in parsed):
        raise ServiceConfigError("playbook must be a nonempty list of objects")
    for play in parsed:
        tasks = play.get("tasks", [])
        if not isinstance(tasks, list) or not all(
            isinstance(task, dict) and ("name" not in task or isinstance(task["name"], str)) for task in tasks
        ):
            raise ServiceConfigError("playbook tasks must be a list of objects with string names")
    if "tasks" not in parsed[0]:
        return []  # ansible-galaxy playbooks may contain only roles
    return [{"name": "Gathering Facts"}, *[{"name": task["name"]} for task in parsed[0]["tasks"] if "name" in task]]
