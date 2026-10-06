"""
The orphan cleanup racing the deploy task's own finish, against the real database.

Each side runs on its own connection/transaction (like two concurrent API
requests), so this exercises the database row locks rather than the test
suite's shared rolling-back session.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.adapters import repository
from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.domain import commands, model
from deploy.service_layer import unit_of_work

pytestmark = pytest.mark.asyncio

PAUSE = 0.3


async def make_bus(publisher, services_filesystem):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
    uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
    await uow.connect()
    return await bootstrap(
        start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
    )


async def add_orphan(bus) -> int:
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    service = model.Service(name="orphan-race", data={})
    async with bus.uow as uow:
        await uow.services.add(service)
        await uow.commit()
        deployment = model.Deployment(service_id=service.id, origin="test", user="test", started=old)
        await uow.deployments.add(deployment)
        await uow.commit()
        await uow.steps.add(
            model.Step(name="done", state="success", deployment_id=deployment.id, started=old, finished=old)
        )
        await uow.commit()
    assert deployment.id is not None
    return deployment.id


async def load(bus, deployment_id):
    async with bus.uow as uow:
        deployment = await uow.deployments.get(deployment_id)
        steps = await uow.steps.get_steps_by_deployment(deployment_id)
    return deployment, steps


async def race(publisher, services_filesystem, first, second):
    setup_bus = await make_bus(publisher, services_filesystem)
    deployment_id = await add_orphan(setup_bus)
    cleanup_bus = await make_bus(publisher, services_filesystem)
    finish_bus = await make_bus(publisher, services_filesystem)
    buses = {
        "cleanup": (cleanup_bus, commands.FinishOrphanedDeployment(deployment_id=deployment_id)),
        "finish": (finish_bus, commands.FinishDeployment(deployment_id=deployment_id)),
    }
    try:
        first_bus, first_cmd = buses[first]
        second_bus, second_cmd = buses[second]
        first_task = asyncio.create_task(first_bus.handle(first_cmd))
        await asyncio.sleep(PAUSE / 3)
        second_result = await asyncio.wait_for(second_bus.handle(second_cmd), timeout=10)
        # whether the second command had to wait until the first one committed
        second_waited = first_task.done()
        first_result = await asyncio.wait_for(first_task, timeout=10)
        results = {first: first_result, second: second_result, "second_waited": second_waited}
        deployment, steps = await load(setup_bus, deployment_id)
    finally:
        for bus in (setup_bus, cleanup_bus, finish_bus):
            await bus.uow.close()
    return results, deployment, steps


async def test_finish_committed_while_cleanup_waits_is_not_marked_failed(
    database, publisher, services_filesystem, monkeypatch
):
    """The deploy task finishes after the cleanup classified the deployment but before it locked it."""
    original = repository.SqlAlchemyServiceRepository.lock_for_deployment

    async def slow_lock_for_deployment(self, service_id):
        await original(self, service_id)
        await asyncio.sleep(PAUSE)

    monkeypatch.setattr(repository.SqlAlchemyServiceRepository, "lock_for_deployment", slow_lock_for_deployment)

    results, deployment, steps = await race(publisher, services_filesystem, "cleanup", "finish")

    assert results["cleanup"] is False
    assert results["second_waited"] is False
    assert deployment.finished is not None
    assert [(step.name, step.state) for step in steps] == [("done", "success")]


async def test_finish_waits_for_cleanup_and_keeps_failure(database, publisher, services_filesystem, monkeypatch):
    """The cleanup holds the deployment lock; the deploy task's finish waits and does not undo the failure."""
    original = repository.SqlAlchemyDeploymentRepository.get_for_update
    calls = []

    async def slow_get_for_update(self, deployment_id):
        result = await original(self, deployment_id)
        calls.append(deployment_id)
        if len(calls) == 1:
            # only the cleanup (first caller) pauses while holding the lock
            await asyncio.sleep(PAUSE)
        return result

    monkeypatch.setattr(repository.SqlAlchemyDeploymentRepository, "get_for_update", slow_get_for_update)

    results, deployment, steps = await race(publisher, services_filesystem, "cleanup", "finish")

    assert results["cleanup"] is True
    # the finish blocked on the deployment lock instead of committing under the cleanup
    assert results["second_waited"] is True
    assert deployment.finished is not None
    assert sorted((step.name, step.state) for step in steps) == [
        ("deployment orphaned", "failure"),
        ("done", "success"),
    ]
