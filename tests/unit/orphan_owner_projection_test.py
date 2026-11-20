import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import NoResultFound

from deploy.domain import commands, model
from deploy.service_layer.handlers import finish_orphaned_deployment


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True], ids=["step-arrives", "deployment-deleted"])
async def test_orphan_cleanup_reads_steps_only_after_service_lock(in_memory_uow, monkeypatch, deleted):
    uow = in_memory_uow
    old = datetime.now(timezone.utc) - timedelta(days=1)
    deployment = model.Deployment(service_id=1, started=old, origin="test", user="test")
    await uow.deployments.add(deployment)
    for number in range(1000):
        await uow.steps.add(
            model.Step(name=f"step-{number}", deployment_id=deployment.id, state="success", started=old, finished=old)
        )

    waiting = asyncio.Event()
    release_lock = asyncio.Event()
    activity = []
    original_get_for_update = uow.deployments.get_for_update
    original_get_steps = uow.steps.get_steps_by_deployment

    async def lock_service(service_id):
        assert service_id == deployment.service_id
        activity.append("service lock requested")
        waiting.set()
        await release_lock.wait()
        activity.append("service locked")

    async def get_for_update(deployment_id):
        activity.append("deployment locked")
        if deleted:
            raise NoResultFound
        return await original_get_for_update(deployment_id)

    async def get_steps(deployment_id):
        activity.append("steps read")
        return await original_get_steps(deployment_id)

    monkeypatch.setattr(uow.services, "lock_for_deployment", lock_service)
    monkeypatch.setattr(uow.deployments, "get_for_update", get_for_update)
    monkeypatch.setattr(uow.steps, "get_steps_by_deployment", get_steps)
    command = commands.FinishOrphanedDeployment(deployment_id=deployment.id)
    async with asyncio.TaskGroup() as tasks:
        cleanup = tasks.create_task(finish_orphaned_deployment(command, uow))
        try:
            await asyncio.wait_for(waiting.wait(), timeout=5)
            assert activity == ["service lock requested"]
            if not deleted:
                await uow.steps.add(model.Step(name="new report", deployment_id=deployment.id, state="running"))
        finally:
            release_lock.set()

    assert cleanup.result() is False
    assert deployment.finished is None
    expected = ["service lock requested", "service locked", "deployment locked"]
    if not deleted:
        expected.append("steps read")
    assert activity == expected
