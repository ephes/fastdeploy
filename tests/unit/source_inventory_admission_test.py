"""The authoritative inventory is complete or refused under one aggregate budget."""

import errno
import json
from collections import Counter

import pytest

from deploy.adapters import filesystem
from deploy.domain import commands


def write_configs(root, count=3, content=None):
    for number in range(count):
        directory = root / f"service-{number}"
        directory.mkdir()
        (directory / "config.json").write_text(content if content is not None else '{"extension": "Grüße"}')


@pytest.mark.parametrize("limit", ["MAX_SOURCE_SERVICES", "MAX_SOURCE_ENTRIES", "MAX_SOURCE_BYTES", "MAX_SOURCE_WORK"])
def test_whole_inventory_refused_on_aggregate_exhaustion(tmp_path, monkeypatch, limit):
    write_configs(tmp_path)
    monkeypatch.setattr(filesystem, limit, 2, raising=False)
    with pytest.raises(filesystem.ServiceConfigError, match=r"source.*limit"):
        filesystem.Filesystem(tmp_path).get_configs()


def test_directory_scan_counts_nonservice_entries(tmp_path, monkeypatch):
    for number in range(3):
        (tmp_path / str(number)).touch()
    monkeypatch.setattr(filesystem, "MAX_SOURCE_ENTRIES", 2, raising=False)
    with pytest.raises(filesystem.ServiceConfigError, match=r"source.*limit"):
        filesystem.Filesystem(tmp_path).list()


@pytest.mark.parametrize("limit", ["MAX_SOURCE_SERVICES", "MAX_SOURCE_BYTES", "MAX_SOURCE_WORK"])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.asyncio
@pytest.mark.db("in_memory")
async def test_aggregate_refusal_has_no_sync_writes(
    bus, services_filesystem, service_in_db, deployment_in_db, publisher, monkeypatch, limit, force
):
    write_configs(services_filesystem.root)
    monkeypatch.setattr(filesystem, limit, 2, raising=False)
    with pytest.raises(filesystem.ServiceConfigError):
        await bus.handle(commands.SyncServices(force=force))
    async with bus.uow as uow:
        assert [s.id for s in await uow.services.list()] == [service_in_db.id]
        assert [d.id for d in await uow.deployments.list()] == [deployment_in_db.id]
    assert publisher.events == []


def test_actual_utf8_bytes_count_each_config_once(tmp_path, monkeypatch):
    content = '{"extension":"Grüße"}'
    write_configs(tmp_path, count=2, content=content)
    size = 2 * len(content.encode("utf-8"))
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", size, raising=False)
    assert len(filesystem.Filesystem(tmp_path).get_configs()) == 2
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", size - 1)
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()


def test_structural_work_counts_each_config_once(tmp_path, monkeypatch):
    write_configs(tmp_path, count=2, content="{}")
    monkeypatch.setattr(filesystem, "MAX_SOURCE_WORK", 2)
    assert len(filesystem.Filesystem(tmp_path).get_configs()) == 2
    monkeypatch.setattr(filesystem, "MAX_SOURCE_WORK", 1)
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()


def test_shared_playbook_and_exact_inventory_boundary(tmp_path, monkeypatch):
    playbook = tmp_path / "shared.yml"
    play = "- hosts: local\n  tasks: [{name: prepare}]\n"
    playbook.write_text(play)
    config = json.dumps({"ansible_playbook": str(playbook)})
    write_configs(tmp_path, count=9, content=config)
    relative_service = tmp_path / "relative-service"
    relative_service.mkdir()
    (relative_service / "config.json").write_text(relative_config := json.dumps({"ansible_playbook": playbook.name}))
    monkeypatch.setattr(filesystem.settings, "project_root", tmp_path)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_SERVICES", 10)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_ENTRIES", 11)
    reads, parses = [], []
    original_read, original_load = filesystem._read_regular, filesystem._load_document

    def read(root, relative, **kwargs):
        reads.append(root / relative)
        return original_read(root, relative, **kwargs)

    def load(content, **kwargs):
        parses.append(content)
        return original_load(content, **kwargs)

    monkeypatch.setattr(filesystem, "_read_regular", read)
    monkeypatch.setattr(filesystem, "_load_document", load)
    actual_bytes = 9 * len(config.encode()) + len(relative_config.encode()) + len(play.encode())
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", actual_bytes)

    reader = filesystem.Filesystem(tmp_path)
    configs = reader.get_configs()
    expected = [{"name": "Gathering Facts"}, {"name": "prepare"}]
    assert len(configs) == 10
    expected_reads = Counter([*tmp_path.glob("*/config.json"), playbook])
    expected_parses = Counter({config: 9, relative_config: 1, play: 1})
    assert Counter(reads) == expected_reads
    assert Counter(parses) == expected_parses
    assert all(data["steps"] == expected for _, data in configs)
    configs[0][1]["steps"][0]["name"] = "changed"
    configs[0][1]["steps"].pop()
    assert all(data["steps"] == expected for _, data in configs[1:])
    assert all(data["steps"] == expected for _, data in reader.get_configs())
    assert Counter(reads) == expected_reads + expected_reads
    assert Counter(parses) == expected_parses + expected_parses

    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", actual_bytes - 1)
    with pytest.raises(filesystem.ServiceConfigError, match="total byte limit"):
        reader.get_configs()


def test_shared_playbook_change_after_parse_refuses_inventory(tmp_path, monkeypatch):
    playbook = tmp_path / "shared.yml"
    playbook.write_text("- hosts: local\n  tasks: [{name: prepare}]\n")
    write_configs(tmp_path, count=10, content=json.dumps({"ansible_playbook": str(playbook)}))
    original_load = filesystem._load_document
    parses = 0

    def load_and_change(content, **kwargs):
        nonlocal parses
        result = original_load(content, **kwargs)
        if kwargs.get("playbook"):
            parses += 1
            playbook.write_text("- hosts: local\n  tasks: [{name: changed after parsing}]\n")
        return result

    monkeypatch.setattr(filesystem, "_load_document", load_and_change)
    with pytest.raises(filesystem.ServiceConfigError, match="tree changed; retry sync"):
        filesystem.Filesystem(tmp_path).get_configs()
    assert parses == 1


def test_directory_scan_stops_before_materializing_excess_entries(tmp_path, monkeypatch):
    from contextlib import contextmanager

    for number in range(10):
        (tmp_path / str(number)).touch()
    original = filesystem.os.scandir
    visited = []

    @contextmanager
    def scan(path):
        with original(path) as entries:

            def limited():
                for entry in entries:
                    visited.append(entry.name)
                    assert len(visited) <= 3, "directory enumeration exceeded admission"
                    yield entry

            yield limited()

    monkeypatch.setattr(filesystem.os, "scandir", scan)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_ENTRIES", 2)
    with pytest.raises(filesystem.ServiceConfigError, match=r"source.*limit"):
        filesystem.Filesystem(tmp_path).list()
    assert len(visited) == 3


def test_stream_construction_failure_closes_config_descriptor(tmp_path, monkeypatch):
    write_configs(tmp_path, count=1)
    descriptors = []

    def fail_fdopen(descriptor, *args, **kwargs):
        filesystem.os.fstat(descriptor)
        descriptors.append(descriptor)
        raise OSError("synthetic stream construction failure")

    monkeypatch.setattr(filesystem.os, "fdopen", fail_fdopen)
    try:
        with pytest.raises(filesystem.ServiceConfigError, match=r"^service config file is unavailable or invalid$"):
            filesystem.Filesystem(tmp_path).get_configs()
        [descriptor] = descriptors
        with pytest.raises(OSError) as closed:
            filesystem.os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF
    finally:
        for descriptor in descriptors:
            try:
                filesystem.os.close(descriptor)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise


def test_reads_stop_at_remaining_total_bytes_plus_one(tmp_path, monkeypatch):
    write_configs(tmp_path, count=1, content='{"extension": "' + "x" * 1000 + '"}')
    original = filesystem.os.fdopen
    sizes, received = [], []

    class Reader:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, size):
            sizes.append(size)
            content = self.source.read(size)
            received.append(len(content))
            return content

    monkeypatch.setattr(filesystem.os, "fdopen", lambda *args, **kwargs: Reader(original(*args, **kwargs)))
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", 10)
    with pytest.raises(filesystem.ServiceConfigError, match="total byte limit"):
        filesystem.Filesystem(tmp_path).get_configs()
    assert sizes == received == [11]


def test_short_reads_are_collected_until_eof(tmp_path, monkeypatch):
    content = '{"extension": "' + "x" * 100 + '"}'
    write_configs(tmp_path, count=1, content=content)
    original = filesystem.os.fdopen
    sizes = []

    class ShortReader:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, size):
            sizes.append(size)
            return self.source.read(min(size, 7))

    monkeypatch.setattr(filesystem.os, "fdopen", lambda *args, **kwargs: ShortReader(original(*args, **kwargs)))
    [(name, config)] = filesystem.Filesystem(tmp_path).get_configs()
    assert name == "service-0"
    assert config["extension"] == "x" * 100
    assert len(sizes) > 2


def test_read_shorter_than_file_size_is_refused(tmp_path, monkeypatch):
    write_configs(tmp_path, count=1, content='{"extension": "' + "x" * 100 + '"}')
    original = filesystem.os.fdopen

    class TruncatingReader:
        def __init__(self, source):
            self.source = source
            self.done = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, size):
            if self.done:
                return b""
            self.done = True
            return self.source.read(10)

    monkeypatch.setattr(filesystem.os, "fdopen", lambda *args, **kwargs: TruncatingReader(original(*args, **kwargs)))
    with pytest.raises(filesystem.ServiceConfigError, match="changed during read"):
        filesystem.Filesystem(tmp_path).get_configs()
