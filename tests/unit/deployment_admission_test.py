"""Synthetic startup and whole-sync admission regressions."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from deploy import views
from deploy.adapters.filesystem import ServiceConfigError
from deploy.config import Settings
from deploy.domain import commands, model


@pytest.mark.parametrize("minutes,runtime", [(1, 1800), (30, 1800), (75, 1770)])
def test_deployment_token_must_cover_runtime_and_finalization(minutes, runtime):
    with pytest.raises(ValidationError, match=r"deployment.*token"):
        Settings(
            _env_file=None,
            secret_key="fixture-key",
            path_for_deploy="/tmp/fixture",
            deployment_access_token_expire_minutes=minutes,
            deployment_max_runtime_seconds=runtime,
        )


def test_open_step_remains_active_through_runtime_and_finalization(monkeypatch):
    # 30s teardown + two (8 x 10s requests + 1270s backoff) + 1s JWT rounding.
    runtime, finalization = 1829, 2731
    configured = Settings(
        _env_file=None,
        secret_key="fixture-key",
        path_for_deploy="/tmp/fixture",
        deployment_access_token_expire_minutes=76,
        deployment_max_runtime_seconds=runtime,
    )
    monkeypatch.setattr(
        views, "STALE_DEPLOYMENT_AGE", timedelta(minutes=configured.deployment_access_token_expire_minutes)
    )
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    deployment = model.Deployment(id=1, service_id=1, origin="test", user="test", started=started)
    steps = [model.Step(name="running", state="running")]
    for elapsed in (runtime, runtime + finalization - 0.001):
        assert (
            views.classify_unfinished_deployment(deployment, steps, started + timedelta(seconds=elapsed)) == "active"
        )
    assert views.classify_unfinished_deployment(deployment, steps, started + timedelta(minutes=76)) == "stale"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            secret_key="fixture-key",
            path_for_deploy="/tmp/fixture",
            deployment_access_token_expire_minutes=76,
            deployment_max_runtime_seconds=runtime + 0.001,
        )


DUPLICATE_DOCUMENTS = [
    ('{"ansible_playbook":"missing.yml","ansible_playbook":"play.yml"}', "- hosts: local\n"),
    ('{"extension":{"private-sentinel":1,"private-sentinel":2}}', None),
    (
        '{"ansible_playbook":"play.yml"}',
        "- hosts: local\n  tasks:\n    - name: private-sentinel\n      name: replaced\n",
    ),
    ('{"ansible_playbook":"play.yml"}', "- hosts: local\n  vars: {private-sentinel: 1, private-sentinel: 2}\n"),
    ('{"ansible_playbook":"play.yml"}', "- hosts: local\n  hosts: replaced\n"),
    ('{"ansible_playbook":"play.yml"}', "- hosts: local\n  vars: {<<: {one: 1}, <<: {two: 2}}\n"),
    ('{"ansible_playbook":"play.yml"}', "- hosts: local\n  vars: {<<: {one: 1}, one: 2}\n"),
    ('{"ansible_playbook":"play.yml"}', "- hosts: local\n  tasks: [{name: ''}]\n"),
    ('{"ansible_playbook":"play.yml","steps":null}', "- hosts: local\n"),
]

INVALID_DEFINITIONS = [
    {"steps": value}
    for value in (
        None,
        "private-sentinel",
        [1],
        [{}],
        [{"name": None}],
        [{"name": 12}],
        [{"name": ""}],
        [{"name": " "}],
        [{"name": "bad\u0000name"}],
        [{"name": "n" * 256}],
    )
] + [{"deploy_script": value} for value in (None, 12, False, [], {}, "", " ", "bad\u0000path")]


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize(
    "content,playbook", DUPLICATE_DOCUMENTS + [(json.dumps(data), None) for data in INVALID_DEFINITIONS]
)
async def test_invalid_snapshot_refused_before_any_sync_mutation(
    bus, services_filesystem, service_in_db, publisher, monkeypatch, content, playbook
):
    root = services_filesystem.root
    monkeypatch.setattr("deploy.config.settings.project_root", root)
    # A valid replacement preceding the bad source must not update the stored service.
    existing = root / service_in_db.name
    existing.mkdir()
    (existing / "config.json").write_text('{"description":"replacement"}')
    bad = root / "invalid"
    bad.mkdir()
    (bad / "config.json").write_text(content)
    if playbook is not None:
        (root / "play.yml").write_text(playbook)
    original_list = services_filesystem.list
    monkeypatch.setattr(
        services_filesystem, "list", lambda: sorted(original_list(), key=lambda name: name == "invalid")
    )
    before = service_in_db.data.copy()
    with pytest.raises(ServiceConfigError) as error:
        await bus.handle(commands.SyncServices(force=True))
    assert "private-sentinel" not in str(error.value)
    async with bus.uow as uow:
        [stored] = await uow.services.list()
        assert stored.id == service_in_db.id
        assert stored.name == service_in_db.name
        assert stored.data == before
    assert publisher.events == []


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
async def test_valid_extension_fields_and_yaml_aliases_survive_sync(bus, services_filesystem, monkeypatch):
    root = services_filesystem.root
    monkeypatch.setattr("deploy.config.settings.project_root", root)
    config = {
        "deploy_script": "runner with spaces.py",
        "steps": [{"name": "configured", "extension": {"opaque": True}}],
        "extension": {"nested": [1, "two", None]},
    }
    directory = root / "json-service"
    directory.mkdir()
    (directory / "config.json").write_text(json.dumps(config))
    directory = root / "yaml-service"
    directory.mkdir()
    (directory / "config.json").write_text('{"ansible_playbook":"play.yml"}')
    (root / "play.yml").write_text(
        "- hosts: local\n  vars: {one: &shared {value: 1}, two: *shared}\n  tasks:\n    - &task {name: synthetic}\n    - *task\n"
    )
    await bus.handle(commands.SyncServices())
    async with bus.uow as uow:
        services = {service.name: service.data for service in await uow.services.list()}
    assert services["json-service"] == config
    assert services["yaml-service"]["steps"] == [
        {"name": "Gathering Facts"},
        {"name": "synthetic"},
        {"name": "synthetic"},
    ]
