import abc
import contextlib
import json
import math
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
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

    def get_configs(self) -> Sequence[tuple[str, dict]]:
        """Prepare a complete source set before synchronization can mutate storage."""
        return [(name, self.get_config_by_name(name)) for name in self.list()]


MAX_CONFIG_BYTES = 1024 * 1024
MAX_CONFIG_DEPTH = 32
MAX_CONFIG_NODES = 50000
# One inventory, including repeated discovery/preparation reads and shared playbooks.
MAX_SOURCE_ENTRIES = 4096
MAX_SOURCE_SERVICES = 1000
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_WORK = 500000


class ServiceConfigError(ValueError):
    """A bounded, value-free service configuration admission failure."""


@dataclass
class _SourceBudget:
    bytes_read: int = 0
    work: int = 0

    def add_bytes(self, count: int):
        self.bytes_read += count
        if self.bytes_read > MAX_SOURCE_BYTES:
            raise ServiceConfigError("service source exceeds total byte limit")

    def add_work(self, count: int = 1):
        self.work += count
        if self.work > MAX_SOURCE_WORK:
            raise ServiceConfigError("service source exceeds total work limit")


def _relative_parts(path: Path) -> tuple[str, ...]:
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ServiceConfigError("service config path is outside approved roots")
    return path.parts


def _generation(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _remember(observed, path, metadata):
    if observed is not None:
        generation = _generation(metadata)
        if path in observed and observed[path] != generation:
            raise ServiceConfigError("service configuration tree changed; retry sync")
        observed[path] = generation


def _read_regular(root: Path, relative: Path, *, observed=None, budget=None) -> str:
    """Walk below an operator-selected root using pinned no-follow descriptors."""
    parts = _relative_parts(relative)
    try:
        with contextlib.ExitStack() as stack:
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, directory)
            current = root
            _remember(observed, current, os.fstat(directory))
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                stack.callback(os.close, directory)
                current = current / part
                _remember(observed, current, os.fstat(directory))
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            stack.callback(os.close, descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
                raise ServiceConfigError("service config must be a regular file of at most 1 MiB")
            _remember(observed, root / relative, metadata)
            # ExitStack owns the descriptor through stream setup and the final fstat.
            with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as source:
                read_limit = MAX_CONFIG_BYTES
                if budget is not None:
                    read_limit = min(read_limit, MAX_SOURCE_BYTES - budget.bytes_read)
                # Unbuffered reads may return short; collect until EOF or the bound.
                chunks: list[bytes] = []
                remaining = read_limit + 1
                while remaining > 0:
                    chunk = source.read(remaining)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
            if budget is not None:
                budget.add_bytes(len(content))
            if _generation(metadata) != _generation(os.fstat(descriptor)):
                raise ServiceConfigError("service config changed during read; retry sync")
            if len(content) > MAX_CONFIG_BYTES:
                raise ServiceConfigError("service config exceeds 1 MiB")
            if len(content) != metadata.st_size:
                raise ServiceConfigError("service config changed during read; retry sync")
            return content.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ServiceConfigError):
            raise
        raise ServiceConfigError("service config file is unavailable or invalid") from None


def _lstat_service_file(path: Path):
    # A config.json or referenced playbook that does not exist is not fixed by
    # retrying sync; other races keep the caller's retry message.
    try:
        return path.lstat()
    except FileNotFoundError:
        raise ServiceConfigError("service config file is unavailable or invalid") from None


def _check_structure(value, *, budget=None):
    # Iterative traversal also bounds recursive/shared YAML aliases.
    pending = [(value, 1)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if budget is not None:
            budget.add_work()
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
    def __init__(self, stream, *, budget=None):
        super().__init__(stream)
        self.source_budget = budget

    def _merge_size(self, node, visiting):
        sizes = self.__dict__.setdefault("_merge_sizes", {})
        identity = id(node)
        if identity in visiting:
            raise ServiceConfigError("recursive playbook merges are not supported")
        if identity in sizes:
            return sizes[identity]
        visiting.add(identity)
        size = 0
        for key, value in node.value:
            if key.tag == "tag:yaml.org,2002:merge":
                sources = value.value if isinstance(value, yaml.SequenceNode) else [value]
                for source in sources:
                    if isinstance(source, yaml.MappingNode):
                        size += self._merge_size(source, visiting)
                        if size > MAX_CONFIG_NODES:
                            raise ServiceConfigError("playbook merge expansion exceeds node limit")
            else:
                size += 1
            if size > MAX_CONFIG_NODES:
                raise ServiceConfigError("playbook merge expansion exceeds node limit")
        visiting.remove(identity)
        sizes[identity] = size
        return size

    def _meter_merge_work(self, node):
        size = self._merge_size(node, set())
        work = self.__dict__.get("_merge_work", 0) + size
        if work > MAX_CONFIG_NODES:
            raise ServiceConfigError("playbook merge expansion exceeds node limit")
        if self.source_budget is not None:
            self.source_budget.add_work(size)
        self.__dict__["_merge_work"] = work

    def flatten_mapping(self, node):
        # Meter projected output before PyYAML allocates flattened merge pairs.
        # PyYAML flattens merge sources by calling this method recursively. A
        # source without its own merge key allocates nothing there (the caller's
        # projected size already includes it), so it is not counted twice; a
        # source that still holds a merge key materializes pairs and is metered.
        if self.__dict__.get("_flattening_merge"):
            if any(key.tag == "tag:yaml.org,2002:merge" for key, _ in node.value):
                self._meter_merge_work(node)
            return super().flatten_mapping(node)
        self._meter_merge_work(node)
        self.__dict__["_flattening_merge"] = True
        try:
            return super().flatten_mapping(node)
        finally:
            self.__dict__["_flattening_merge"] = False

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


def _finite_json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ServiceConfigError("service config numbers must be finite")
    return number


def _reject_json_constant(_value):
    raise ServiceConfigError("service config numbers must be finite")


def _load_document(content: str, *, playbook=False, budget=None):
    try:
        if playbook:
            depth = 0
            for count, event in enumerate(yaml.parse(content), 1):
                if budget is not None:
                    budget.add_work()
                if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                    depth += 1
                elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                    depth -= 1
                if depth > MAX_CONFIG_DEPTH or count > MAX_CONFIG_NODES:
                    raise ServiceConfigError("playbook exceeds depth or node limit")
            loader = _UniqueKeySafeLoader(content, budget=budget)
            try:
                value = loader.get_single_data()
            finally:
                loader.dispose()
        else:
            value = json.loads(
                content,
                object_pairs_hook=_unique_mapping,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
            )
        _check_structure(value, budget=budget)
        return value
    except ServiceConfigError:
        raise
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
        runtime_fields = {"id", "state", "started", "finished", "message", "deployment_id"}
        if any(runtime_fields.intersection(step) for step in steps):
            raise ServiceConfigError("configured steps must not contain runtime fields")


class Filesystem(AbstractFilesystem):
    def list(self):
        """Refuse aliases rather than silently dropping a service during sync."""
        directories = []
        try:
            # Path.iterdir may eagerly materialize the directory on supported Python
            # versions. Stream entries so refusal also bounds discovery allocation.
            with os.scandir(self.root) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > MAX_SOURCE_ENTRIES:
                        raise ServiceConfigError("service source exceeds directory entry limit")
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(mode):
                        raise ServiceConfigError("service directory aliases are not supported")
                    if stat.S_ISDIR(mode):
                        if len(directories) >= MAX_SOURCE_SERVICES:
                            raise ServiceConfigError("service source exceeds service count limit")
                        directories.append(entry.name)
        except OSError:
            raise ServiceConfigError("service configuration root is unavailable") from None
        return directories

    def get_configs(self):
        budget = _SourceBudget()
        observed = {}
        try:
            _remember(observed, self.root, self.root.lstat())
            names = self.list()
            # Capture every selected service/config before reading the first one.
            for name in names:
                directory = self.root / name
                _remember(observed, directory, directory.lstat())
                _remember(observed, directory / "config.json", _lstat_service_file(directory / "config.json"))
            # Discover referenced files before preparing any service. A playbook
            # selected by a later service must not change unnoticed during earlier reads.
            for name in names:
                data = _load_document(
                    _read_regular(self.root, Path(name) / "config.json", observed=observed, budget=budget),
                    budget=budget,
                )
                if isinstance(data, dict) and "ansible_playbook" in data:
                    root, relative = _playbook_location(data["ansible_playbook"], self.root)
                    path = root / relative
                    _remember(observed, path, _lstat_service_file(path))
            configs = [(name, self.get_config_by_name(name, observed=observed, budget=budget)) for name in names]
            # Include referenced playbooks and the descriptor-walk directories.
            for path, generation in observed.items():
                if _generation(path.lstat()) != generation:
                    raise ServiceConfigError("service configuration tree changed; retry sync")
            return configs
        except OSError:
            raise ServiceConfigError("service configuration tree changed or is unavailable; retry sync") from None

    def get_config_by_name(self, name, *, observed=None, budget=None):
        if budget is None:
            budget = _SourceBudget()
        if not isinstance(name, str) or len(Path(name).parts) != 1 or name in (".", ".."):
            raise ServiceConfigError("invalid service directory name")
        data_dict = _load_document(
            _read_regular(self.root, Path(name) / "config.json", observed=observed, budget=budget), budget=budget
        )
        if not isinstance(data_dict, dict):
            raise ServiceConfigError("service config must be an object")
        _validate_service_definition(data_dict)
        if "ansible_playbook" in data_dict:
            data_dict["steps"] = get_steps_from_playbook(
                data_dict["ansible_playbook"], config_root=self.root, observed=observed, budget=budget
            )
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


def _playbook_location(path_from_config: str, config_root: Path | None = None) -> tuple[Path, Path]:
    if not isinstance(path_from_config, str) or not path_from_config or "\x00" in path_from_config:
        raise ServiceConfigError("invalid playbook path")
    path = Path(path_from_config)
    if ".." in path.parts:
        raise ServiceConfigError("playbook parent traversal is not supported")
    roots = [settings.project_root, *settings.service_playbook_roots]
    if config_root is not None:
        roots.append(config_root)
    if not path.is_absolute():
        return settings.project_root, path
    else:
        for root in roots:
            root = root.absolute()
            if path.is_relative_to(root):
                return root, path.relative_to(root)
        else:
            raise ServiceConfigError("playbook path is outside approved roots")


def get_steps_from_playbook(
    path_from_config: str, *, config_root: Path | None = None, observed=None, budget=None
) -> list[dict]:
    """Read an admitted playbook below the project/config or approved extra roots."""
    if budget is None:
        budget = _SourceBudget()
    root, relative = _playbook_location(path_from_config, config_root)
    content = _read_regular(root, relative, observed=observed, budget=budget)
    parsed = _load_document(content, playbook=True, budget=budget)
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
