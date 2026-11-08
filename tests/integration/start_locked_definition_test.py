import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from deploy.adapters import repository
from deploy.domain import commands, model

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("with_history", [False, True])
async def test_start_uses_definition_synced_before_lock(
    independent_bus, services_filesystem, monkeypatch, with_history
):
    setup = await independent_bus()
    old = {"deploy_script": "old.py", "steps": [{"name": "old"}]}
    new = {"deploy_script": "new.py", "steps": [{"name": "new"}, {"name": "verify"}]}
    service = model.Service(name="snapshot", data=old)
    async with setup.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    if with_history:
        now = datetime.now(timezone.utc)
        async with setup.uow as uow:
            previous = model.Deployment(service_id=service.id, origin="test", user="test", started=now, finished=now)
            await uow.deployments.add(previous)
            await uow.flush()
            await uow.steps.add(
                model.Step(name="historical", state="success", deployment_id=previous.id, started=now, finished=now)
            )
            await uow.commit()
    directory = services_filesystem.root / service.name
    directory.mkdir()
    (directory / "config.json").write_text(json.dumps(new))

    waiting, resume = asyncio.Event(), asyncio.Event()
    original = repository.SqlAlchemyServiceRepository.lock_for_deployment

    async def pause_before_lock(self, service_id):
        waiting.set()
        await resume.wait()
        await original(self, service_id)

    monkeypatch.setattr(repository.SqlAlchemyServiceRepository, "lock_for_deployment", pause_before_lock)
    launched = Mock()
    monkeypatch.setattr(model.Deployment, "start_deployment_task", launched)
    starter = await independent_bus()
    original_flush = starter.uow.flush

    async def assert_lock_then_flush():
        # PostgreSQL retains this service table lock until transaction end.
        # A nested planning UOW rollback would drop it before admission.
        assert await starter.uow.connection.scalar(
            text(
                "select exists(select 1 from pg_locks where pid=pg_backend_pid() "
                "and relation='service'::regclass and mode='RowShareLock' and granted)"
            )
        )
        await original_flush()

    monkeypatch.setattr(starter.uow, "flush", assert_lock_then_flush)
    task = asyncio.create_task(
        starter.handle(commands.StartDeployment(service_id=service.id, origin="test", user="test", context={}))
    )
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        syncer = await independent_bus()
        await syncer.handle(commands.SyncServices())
    finally:
        resume.set()
        await asyncio.wait_for(task, 5)

    assert launched.call_count == 1
    assert launched.call_args.args[0].data == new
    async with setup.uow as uow:
        deployment = max(await uow.deployments.get_by_service(service.id), key=lambda d: d.id)
        steps = await uow.steps.get_steps_by_deployment(deployment.id)
    expected = [("historical", "running")] if with_history else [("new", "running"), ("verify", "pending")]
    assert [(s.name, s.state) for s in steps] == expected
