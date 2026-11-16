"""Fresh plans persist independently from old result rows, before child launch."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from deploy.adapters.filesystem import ServiceConfigError
from deploy.domain import commands, model

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("source", ["history", "legacy_config"])
async def test_new_plan_reopened_before_first_report_has_clean_results(independent_bus, monkeypatch, source):
    setup, starter, reader = [await independent_bus() for _ in range(3)]
    now = datetime.now(timezone.utc) - timedelta(days=1)
    async with setup.uow as uow:
        service = model.Service(name="sample", data={})
        await uow.services.add(service)
        await uow.flush()
        old_deployment = model.Deployment(service_id=service.id, origin="test", user="test", started=now, finished=now)
        await uow.deployments.add(old_deployment)
        await uow.flush()
        old_steps = [
            model.Step(
                name=name,
                state="success" if source == "history" else "failure",
                started=now,
                finished=now,
                deployment_id=old_deployment.id,
                message=f"OLD OUTPUT {name}",
            )
            for name in ("prepare", "verify")
        ]
        for step in old_steps:
            await uow.steps.add(step)
        await uow.flush()
        if source == "legacy_config":
            # Stored pre-admission definitions may contain runtime keys, even colliding ids.
            service.data = {
                "steps": [
                    {**s.model_dump(), "started": now.isoformat(), "finished": now.isoformat()} for s in old_steps
                ]
            }
            await uow.services.add(service)
        await uow.commit()
    before = [s.model_dump() for s in old_steps]
    launches = []
    monkeypatch.setattr(model.Deployment, "start_deployment_task", lambda self, _: launches.append(self.id))
    await starter.handle(commands.StartDeployment(service_id=service.id, origin="test", user="test", context={}))
    assert len(launches) == 1
    async with reader.uow as uow:
        fresh = await uow.steps.get_steps_by_deployment(launches[0])
        old = await uow.steps.get_steps_by_deployment(old_deployment.id)
    assert [(s.name, s.state, s.message, s.finished) for s in fresh] == [
        ("prepare", "running", "", None),
        ("verify", "pending", "", None),
    ]
    assert all(s.deployment_id == launches[0] and s.id not in [o.id for o in old] for s in fresh)
    assert [s.model_dump() for s in old] == before


@pytest.mark.parametrize("force", [False, True])
async def test_runtime_config_refusal_preserves_history(independent_bus, services_filesystem, monkeypatch, force):
    setup, syncer = [await independent_bus() for _ in range(2)]
    async with setup.uow as uow:
        service = model.Service(name="keep", data={})
        await uow.services.add(service)
        await uow.flush()
        deployment = model.Deployment(service_id=service.id, origin="test", user="test")
        await uow.deployments.add(deployment)
        await uow.flush()
        step = model.Step(name="history", deployment_id=deployment.id, state="success", message="HISTORY")
        await uow.steps.add(step)
        await uow.commit()
    directory = services_filesystem.root / "new"
    directory.mkdir()
    (directory / "config.json").write_text(json.dumps({"steps": [{"name": "prepare", "id": step.id}]}))
    launches = []
    monkeypatch.setattr(model.Deployment, "start_deployment_task", lambda *args: launches.append(args))
    with pytest.raises(ServiceConfigError):
        await syncer.handle(commands.SyncServices(force=force))
    async with setup.uow as uow:
        assert [s.id for s in await uow.services.list()] == [service.id]
        assert [d.id for d in await uow.deployments.list()] == [deployment.id]
        [unchanged] = await uow.steps.get_steps_by_deployment(deployment.id)
        assert unchanged.model_dump() == step.model_dump()
    assert launches == []
