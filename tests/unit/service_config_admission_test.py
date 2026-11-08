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
