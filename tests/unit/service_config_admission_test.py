"""Synthetic service/playbook admission refuses before sync mutation."""

import json
import os
from pathlib import Path

import pytest

from deploy.adapters import filesystem
from deploy.config import settings
from deploy.domain import commands


def config_file(root, content):
    directory = root / "sample"
    directory.mkdir(exist_ok=True)
    path = directory / "config.json"
    path.write_text(content)
    return path


@pytest.mark.parametrize("kind", ["oversize", "deep", "playbook-shape", "yaml-depth", "yaml-alias"])
def test_budget_and_shapes(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(filesystem, "MAX_CONFIG_BYTES", 256, raising=False)
    if kind == "oversize":
        content = json.dumps({"padding": "x" * 300})
    elif kind == "deep":
        content = '{"nested":' + "[" * 40 + "0" + "]" * 40 + "}"
    else:
        playbook = tmp_path / "play.yml"
        playbook.write_text(
            {
                "playbook-shape": "- hosts: local\n  tasks: invalid\n",
                "yaml-depth": "- hosts: local\n  vars: " + "[" * 40 + "0" + "]" * 40,
                "yaml-alias": "- &loop {vars: *loop}\n",
            }[kind]
        )
        content = json.dumps({"ansible_playbook": str(playbook)})
    config_file(tmp_path, content)
    with pytest.raises(ValueError):
        filesystem.Filesystem(tmp_path).get_config_by_name("sample")


def test_fifo_refused_without_blocking(tmp_path, monkeypatch):
    path = config_file(tmp_path, "{}")
    path.unlink()
    os.mkfifo(path)
    original = Path.open

    def guard(self, *args, **kwargs):
        if self == path:
            pytest.fail("ordinary blocking path open would wait on the FIFO")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard)
    with pytest.raises(ValueError):
        filesystem.Filesystem(tmp_path).get_config_by_name("sample")


@pytest.mark.parametrize("alias", ["directory", "config", "playbook", "traversal"])
def test_outside_alias_refused(tmp_path, monkeypatch, alias):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "config.json").write_text("{}")
    playbook = outside / "play.yml"
    playbook.write_text("- hosts: local\n")
    config = config_file(root, "{}")
    monkeypatch.setattr(settings, "project_root", root)
    if alias == "directory":
        config.unlink()
        config.parent.rmdir()
        config.parent.symlink_to(outside, target_is_directory=True)
    elif alias == "config":
        config.unlink()
        config.symlink_to(outside / "config.json")
    elif alias == "playbook":
        (root / "play.yml").symlink_to(playbook)
        config.write_text(json.dumps({"ansible_playbook": "play.yml"}))
    else:
        config.write_text(json.dumps({"ansible_playbook": "../outside/play.yml"}))
    with pytest.raises(ValueError):
        filesystem.Filesystem(root).get_config_by_name("sample")


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
async def test_bad_config_keeps_all_services(bus, services_filesystem, service_in_db, publisher, monkeypatch):
    config_file(services_filesystem.root, '{"ansible_playbook": 12}')
    with pytest.raises(ValueError):
        await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        assert [s.name for s in await uow.services.list()] == [service_in_db.name]
    assert publisher.events == []


@pytest.mark.parametrize("target", ["leaf", "parent"])
def test_swap_during_open_refuses_outside_bytes(tmp_path, monkeypatch, target):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    config = config_file(root, "{}")
    (outside / "config.json").write_text('{"secret": "outside"}')
    original = os.open
    swapped = []

    def swap(path, flags, *args, **kwargs):
        if path == ("config.json" if target == "leaf" else "sample") and not swapped:
            swapped.append(True)
            if target == "leaf":
                config.unlink()
                config.symlink_to(outside / "config.json")
            else:
                config.parent.rename(root / "original")
                (root / "sample").symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap)
    with pytest.raises(ValueError):
        filesystem.Filesystem(root).get_config_by_name("sample")
    assert swapped


def test_extra_absolute_playbook_root_requires_approval(tmp_path, monkeypatch):
    root, approved = tmp_path / "root", tmp_path / "approved"
    root.mkdir()
    approved.mkdir()
    playbook = approved / "play.yml"
    playbook.write_text("- hosts: local\n  tasks:\n    - name: synthetic\n")
    config_file(root, json.dumps({"ansible_playbook": str(playbook)}))
    monkeypatch.setattr(settings, "project_root", root)
    reader = filesystem.Filesystem(root)
    with pytest.raises(ValueError):
        reader.get_config_by_name("sample")
    monkeypatch.setattr(settings, "service_playbook_roots", [approved])
    assert reader.get_config_by_name("sample")["steps"] == [{"name": "Gathering Facts"}, {"name": "synthetic"}]


@pytest.mark.parametrize("content", [" ", "[]", "{}", "[12]", "- tasks: [12]", "- tasks: [{name: 12}]"])
def test_invalid_playbook_structures(tmp_path, content):
    playbook = tmp_path / "play.yml"
    playbook.write_text(content)
    config_file(tmp_path, json.dumps({"ansible_playbook": str(playbook)}))
    with pytest.raises(ValueError):
        filesystem.Filesystem(tmp_path).get_config_by_name("sample")


@pytest.mark.parametrize("kind", ["fifo", "oversize"])
def test_playbook_file_admission(tmp_path, monkeypatch, kind):
    playbook = tmp_path / "play.yml"
    config_file(tmp_path, json.dumps({"ansible_playbook": str(playbook)}))
    if kind == "fifo":
        os.mkfifo(playbook)
    else:
        monkeypatch.setattr(filesystem, "MAX_CONFIG_BYTES", 256)
        playbook.write_text("#" + "x" * 300)
    with pytest.raises(ValueError):
        filesystem.Filesystem(tmp_path).get_config_by_name("sample")


def test_contained_relative_playbook_and_exact_byte_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "project_root", tmp_path)
    (tmp_path / "play.yml").write_text("- hosts: local\n  tasks:\n    - name: contained\n")
    config = config_file(tmp_path, '{"ansible_playbook":"play.yml"}')
    reader = filesystem.Filesystem(tmp_path)
    assert reader.get_config_by_name("sample")["steps"][-1] == {"name": "contained"}
    monkeypatch.setattr(filesystem, "MAX_CONFIG_BYTES", 128)
    config.write_text("{}" + " " * 126)
    assert reader.get_config_by_name("sample") == {}
    config.write_text("{}" + " " * 127)
    with pytest.raises(ValueError):
        reader.get_config_by_name("sample")


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
async def test_nonfinite_json_refuses_whole_sync(bus, services_filesystem, service_in_db, publisher, number):
    config_file(services_filesystem.root, '{"nested": [{"value": ' + number + "}]}")
    with pytest.raises(filesystem.ServiceConfigError):
        await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        assert [s.name for s in await uow.services.list()] == [service_in_db.name]
    assert publisher.events == []


def test_finite_nested_json_preserved(tmp_path):
    data = {"nested": [{"value": 1e200}, -1e-200, 0, 1234567890]}
    config_file(tmp_path, json.dumps(data))
    assert filesystem.Filesystem(tmp_path).get_config_by_name("sample") == data


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
async def test_merge_expansion_refused_before_flattening(
    bus, services_filesystem, service_in_db, publisher, monkeypatch
):
    import yaml

    content = "- hosts: local\n  vars:\n    base: &v0 {x: 1}\n"
    for i in range(1, 18):
        content += f"    level{i}: &v{i} {{<<: [*v{i - 1}, *v{i - 1}]}}\n"
    # Observe actual work in PyYAML's materializer, independent of admission counters.
    original = yaml.SafeLoader.flatten_mapping
    visits = 0

    def counted(self, node):
        nonlocal visits
        visits += len(node.value)
        assert visits <= filesystem.MAX_CONFIG_NODES, "merge materialization exceeded budget"
        return original(self, node)

    monkeypatch.setattr(yaml.SafeLoader, "flatten_mapping", counted)
    playbook = services_filesystem.root / "play.yml"
    playbook.write_text(content)
    config_file(services_filesystem.root, json.dumps({"ansible_playbook": str(playbook)}))
    with pytest.raises(filesystem.ServiceConfigError):
        await bus.handle(commands.SyncServices(force=True))
    assert visits <= filesystem.MAX_CONFIG_NODES
    async with bus.uow as uow:
        assert [s.name for s in await uow.services.list()] == [service_in_db.name]
    assert publisher.events == []


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("kind", ["config", "playbook"])
async def test_same_inode_overwrite_during_read_is_refused(
    bus, services_filesystem, service_in_db, publisher, monkeypatch, kind
):
    import threading

    tmp_path = services_filesystem.root
    config = config_file(tmp_path, "{}")
    target = config
    before, after = b'{"value": "old"}', b'{"value": "new"}'
    if kind == "playbook":
        target = tmp_path / "play.yml"
        before, after = b"- hosts: old\n", b"- hosts: new\n"
        config.write_text(json.dumps({"ansible_playbook": str(target)}))
    target.write_bytes(before)
    reading, written = threading.Event(), threading.Event()
    original = os.fdopen

    class Reader:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, size):
            content = self.source.read(size)
            if content == before:
                reading.set()
                assert written.wait(5)
            return content

    def overwrite():
        assert reading.wait(5)
        target.write_bytes(after)
        written.set()

    thread = threading.Thread(target=overwrite)
    thread.start()
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: Reader(original(*args, **kwargs)))
    try:
        with pytest.raises(filesystem.ServiceConfigError):
            await bus.handle(commands.SyncServices(force=True))
    finally:
        reading.set()
        thread.join(5)
    assert not thread.is_alive()
    async with bus.uow as uow:
        assert [s.name for s in await uow.services.list()] == [service_in_db.name]
    assert publisher.events == []


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("mutation", ["config", "playbook", "add", "remove", "directory"])
async def test_tree_change_refuses_sync_then_stable_retry_succeeds(
    bus, services_filesystem, service_in_db, publisher, monkeypatch, mutation
):
    root = services_filesystem.root
    config = config_file(root, '{"generation": "old"}')
    playbook = root / "play.yml"
    playbook.write_text("- hosts: local\n")
    config.write_text(json.dumps({"generation": "old", "ansible_playbook": str(playbook)}))
    other = root / "other"
    other.mkdir()
    (other / "config.json").write_text("{}")
    original = services_filesystem.get_config_by_name
    changed = False

    def read_and_change(name, **kwargs):
        nonlocal changed
        data = original(name, **kwargs)
        if not changed:
            changed = True
            if mutation == "config":
                replacement = root / "replacement"
                replacement.write_text('{"generation": "new"}')
                replacement.replace(config)
            elif mutation == "playbook":
                playbook.write_text("- hosts: changed\n")
            elif mutation == "add":
                added = root / "added"
                added.mkdir()
                (added / "config.json").write_text("{}")
            elif mutation == "remove":
                config.unlink()
                config.parent.rmdir()
            else:
                config.parent.rename(root / "renamed")
        return data

    with monkeypatch.context() as scoped:
        scoped.setattr(services_filesystem, "get_config_by_name", read_and_change)
        with pytest.raises(filesystem.ServiceConfigError):
            await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        assert [s.name for s in await uow.services.list()] == [service_in_db.name]
    assert publisher.events == []
    await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        assert service_in_db.name not in [s.name for s in await uow.services.list()]


def test_atomic_replacement_before_read_is_supported(tmp_path):
    config = config_file(tmp_path, '{"generation": "old"}')
    replacement = tmp_path / "replacement"
    replacement.write_text('{"generation": "new"}')
    replacement.replace(config)
    assert filesystem.Filesystem(tmp_path).get_config_by_name("sample") == {"generation": "new"}


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
async def test_finite_settings_roundtrip_service_api(bus, services_filesystem, app, valid_access_token_in_db):
    from httpx import ASGITransport, AsyncClient

    data = {"nested": [{"value": 1e200}, -1e-200, 1234567890]}
    config_file(services_filesystem.root, json.dumps(data))
    await bus.handle(commands.SyncServices(force=True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/services/", headers={"Authorization": f"Bearer {valid_access_token_in_db}"})
    assert response.status_code == 200
    assert response.json()[0]["data"] == data


def test_shared_merge_anchor_is_metered_once_per_materialization(tmp_path):
    # 4,000 tasks each merging a 10-key anchor materialize ~44k pairs: under the
    # 50k ceiling, so nested flattening of the anchor must not be counted again.
    anchor = ", ".join(f"k{i}: {i}" for i in range(10))
    lines = ["- hosts: local", f"  vars: {{base: &b {{{anchor}}}}}", "  tasks:"]
    lines += [f"    - {{name: t{i}, <<: *b}}" for i in range(4000)]
    playbook = tmp_path / "play.yml"
    playbook.write_text("\n".join(lines) + "\n")
    config_file(tmp_path, json.dumps({"ansible_playbook": str(playbook)}))
    configs = filesystem.Filesystem(tmp_path).get_configs()
    assert [name for name, _ in configs] == ["sample"]


@pytest.mark.parametrize("missing", ["config", "playbook"])
def test_missing_service_files_are_not_reported_as_retryable(tmp_path, missing):
    if missing == "config":
        (tmp_path / "sample").mkdir()
    else:
        config_file(tmp_path, json.dumps({"ansible_playbook": str(tmp_path / "absent.yml")}))
    with pytest.raises(filesystem.ServiceConfigError, match="unavailable or invalid") as raised:
        filesystem.Filesystem(tmp_path).get_configs()
    assert "retry" not in str(raised.value)


def test_nested_merge_chain_is_metered_before_materialization(tmp_path, monkeypatch):
    # The consumer sits shallower than the chain, so PyYAML flattens it first and
    # materializes the whole chain through nested flatten_mapping calls.
    import yaml

    monkeypatch.setattr(filesystem, "MAX_CONFIG_NODES", 3000, raising=False)
    keys = lambda level: ", ".join(f"k{level}_{i}: {i}" for i in range(10))  # noqa: E731
    chain = [f"&l0 {{{keys(0)}}}"] + [f"&l{k} {{<<: *l{k - 1}, {keys(k)}}}" for k in range(1, 60)]
    content = "- hosts: local\n  vars:\n    chain: [[" + ", ".join(chain) + "]]\n    consumer: {<<: *l59}\n"
    original = yaml.SafeLoader.flatten_mapping
    materialized = 0

    def counted(self, node):
        nonlocal materialized
        result = original(self, node)
        materialized += len(node.value)
        return result

    monkeypatch.setattr(yaml.SafeLoader, "flatten_mapping", counted)
    playbook = tmp_path / "play.yml"
    playbook.write_text(content)
    config_file(tmp_path, json.dumps({"ansible_playbook": str(playbook)}))
    with pytest.raises(filesystem.ServiceConfigError):
        filesystem.Filesystem(tmp_path).get_configs()
    assert materialized <= filesystem.MAX_CONFIG_NODES
