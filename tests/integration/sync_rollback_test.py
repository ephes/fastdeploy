"""One real sync transaction must cover removals, updates, additions and events."""

import json
from datetime import datetime, timezone

import pytest

from deploy.adapters import repository
from deploy.domain import commands, events, model

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("phase", ["second_delete", "second_save"])
async def test_mid_sync_fault_restores_services_and_history(
    independent_bus, services_filesystem, publisher, monkeypatch, phase
):
    setup, syncer = [await independent_bus() for _ in range(2)]
    now = datetime.now(timezone.utc)
    async with setup.uow as uow:
        for name in ("keep", "gone-a", "gone-b"):
            service = model.Service(name=name, data={"definition": "original"})
            await uow.services.add(service)
            await uow.flush()
            deployment = model.Deployment(service_id=service.id, origin="test", user="test", started=now, finished=now)
            await uow.deployments.add(deployment)
            await uow.flush()
            await uow.steps.add(model.Step(name="history", state="success", deployment_id=deployment.id))
        await uow.commit()

    async def snapshot():
        async with setup.uow as uow:
            services = await uow.services.list()
            deployments = await uow.deployments.list()
            steps = await uow.steps.list()
        return (
            sorted((s.id, s.name, s.data) for s in services),
            sorted((d.id, d.service_id, d.started, d.finished) for d in deployments),
            sorted((s.id, s.deployment_id, s.name, s.state) for s in steps),
        )

    before = await snapshot()
    for name in ("keep", "new"):
        directory = services_filesystem.root / name
        directory.mkdir()
        (directory / "config.json").write_text(json.dumps({"definition": "changed"}))
    # Stable filesystem order ensures the first save is an edit, then an addition.
    monkeypatch.setattr(services_filesystem, "list", lambda: ["keep", "new"])
    method = "_delete" if phase == "second_delete" else "_add"
    original = getattr(repository.SqlAlchemyServiceRepository, method)
    reached = []
    fault = RuntimeError("synthetic mid-sync failure")

    async def fail_second(self, service):
        reached.append(service.name)
        if len(reached) == 2:
            raise fault
        await original(self, service)
        # Actually send the first write/cascade to PostgreSQL before failing.
        await self.session.flush()

    with monkeypatch.context() as scoped:
        scoped.setattr(repository.SqlAlchemyServiceRepository, method, fail_second)
        with pytest.raises(RuntimeError) as error:
            await syncer.handle(commands.SyncServices(force=True))
    assert error.value is fault
    assert len(reached) == 2
    assert await snapshot() == before
    assert publisher.events == []

    retry = await independent_bus()
    result = await retry.handle(commands.SyncServices(force=True))
    assert sorted(result.deleted) == ["gone-a", "gone-b"]
    assert sorted(result.updated) == ["keep", "new"]
    after = await snapshot()
    assert [(name, data) for _, name, data in after[0]] == [
        ("keep", {"definition": "changed"}),
        ("new", {"definition": "changed"}),
    ]
    assert len(after[1]) == len(after[2]) == 1
    assert sorted(event.name for _, event in publisher.events if isinstance(event, events.ServiceUpdated)) == [
        "keep",
        "new",
    ]
    assert sorted(event.name for _, event in publisher.events if isinstance(event, events.ServiceDeleted)) == [
        "gone-a",
        "gone-b",
    ]


async def test_bad_source_preflight_keeps_committed_services(independent_bus, services_filesystem):
    setup, syncer = await independent_bus(), await independent_bus()
    async with setup.uow as uow:
        await uow.services.add(model.Service(name="keep", data={"original": True}))
        await uow.commit()
    for name, content in (("new", "{}"), ("invalid", '{"ansible_playbook": 12}')):
        path = services_filesystem.root / name
        path.mkdir()
        (path / "config.json").write_text(content)
    with pytest.raises(ValueError):
        await syncer.handle(commands.SyncServices(force=True))
    async with setup.uow as uow:
        rows = await uow.services.list()
        assert [(s.name, s.data) for s in rows] == [("keep", {"original": True})]
