"""The authoritative inventory is complete or refused under one aggregate budget."""

import json

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


def test_actual_utf8_bytes_include_both_config_reads(tmp_path, monkeypatch):
    content = '{"extension":"Grüße"}'
    write_configs(tmp_path, count=2, content=content)
    size = 4 * len(content.encode("utf-8"))  # discovery and preparation, two services
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", size, raising=False)
    assert len(filesystem.Filesystem(tmp_path).get_configs()) == 2
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", size - 1)
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()


def test_work_limit_includes_discovery_and_preparation(tmp_path, monkeypatch):
    write_configs(tmp_path, count=2, content="{}")
    monkeypatch.setattr(filesystem, "MAX_SOURCE_WORK", 4, raising=False)
    assert len(filesystem.Filesystem(tmp_path).get_configs()) == 2
    monkeypatch.setattr(filesystem, "MAX_SOURCE_WORK", 3)
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()


def test_shared_playbook_and_exact_inventory_boundary(tmp_path, monkeypatch):
    playbook = tmp_path / "shared.yml"
    play = "- hosts: local\n  tasks: [{name: prepare}]\n"
    playbook.write_text(play)
    config = json.dumps({"ansible_playbook": str(playbook)})
    write_configs(tmp_path, count=2, content=config)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_SERVICES", 2, raising=False)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_ENTRIES", 3, raising=False)
    actual_bytes = 4 * len(config.encode()) + 2 * len(play.encode())
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", actual_bytes, raising=False)
    configs = filesystem.Filesystem(tmp_path).get_configs()
    assert len(configs) == 2
    assert all(data["steps"] == [{"name": "Gathering Facts"}, {"name": "prepare"}] for _, data in configs)
    monkeypatch.setattr(filesystem, "MAX_SOURCE_BYTES", actual_bytes - 1)
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()


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
