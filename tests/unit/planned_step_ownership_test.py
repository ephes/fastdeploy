"""Configuration supplies planning names, never execution identity or results."""

import json
from datetime import datetime, timezone

import pytest

from deploy import views
from deploy.adapters.filesystem import Filesystem, ServiceConfigError
from deploy.domain import commands, model


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("field", ["id", "state", "started", "finished", "message", "deployment_id"])
@pytest.mark.parametrize("playbook", [False, True])
async def test_runtime_step_fields_refuse_whole_sync(
    bus, services_filesystem, service_in_db, deployment_in_db, publisher, field, playbook
):
    root = services_filesystem.root
    directory = root / "new"
    directory.mkdir()
    data = {"steps": [{"name": "prepare", field: 1 if field.endswith("id") else "old result"}]}
    if playbook:
        path = root / "play.yml"
        path.write_text("- hosts: local\n  tasks: [{name: prepare}]\n")
        data["ansible_playbook"] = str(path)
    (directory / "config.json").write_text(json.dumps(data))
    with pytest.raises(ServiceConfigError, match="runtime"):
        await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        assert [s.id for s in await uow.services.list()] == [service_in_db.id]
        assert [d.id for d in await uow.deployments.list()] == [deployment_in_db.id]
    assert publisher.events == []


@pytest.mark.asyncio
async def test_legacy_stored_runtime_fields_cannot_enter_plan():
    service = model.Service(
        name="legacy",
        data={
            "steps": [
                {
                    "name": "prepare",
                    "id": 42,
                    "deployment_id": 9,
                    "state": "failure",
                    "started": "old",
                    "finished": "old",
                    "message": "OLD OUTPUT",
                    "extension": {"x": 1},
                }
            ]
        },
    )
    [step] = await views.get_steps_to_do_from_service(service)
    assert step.model_dump() == model.Step(name="prepare").model_dump()


@pytest.mark.asyncio
async def test_step_extensions_preserved_outside_execution_identity(tmp_path):
    directory = tmp_path / "sample"
    directory.mkdir()
    data = {"steps": [{"name": "prepare", "extension": {"key": "value"}}], "custom": True}
    (directory / "config.json").write_text(json.dumps(data))
    [(name, config)] = Filesystem(tmp_path).get_configs()
    assert config == data
    [step] = await views.get_steps_to_do_from_service(model.Service(name=name, data=config))
    assert step.model_dump() == model.Step(name="prepare").model_dump()


def test_replanned_step_has_no_result_or_execution_association():
    now = datetime.now(timezone.utc)
    old = model.Step(
        id=42,
        name="prepare",
        state="success",
        started=now,
        finished=now,
        deployment_id=9,
        message="DISTINCTIVE OLD OUTPUT",
    )
    before = old.model_dump()
    fresh = model.Step.new_pending_from_old(old)
    assert fresh.model_dump() == model.Step(name="prepare").model_dump()
    assert old.model_dump() == before
