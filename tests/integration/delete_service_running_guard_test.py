"""
Deleting a service must not remove a deployment that is still running.

The concurrency test uses separate connections/transactions (like two API
requests) against the real database, so it exercises the service row lock
shared with deployment starts.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.adapters import repository
from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.domain import commands, model
from deploy.service_layer import unit_of_work

pytestmark = pytest.mark.asyncio


async def add_deployment(uow, service, *, finished=None, step_state="running"):
    deployment = model.Deployment(
        service_id=service.id, origin="test", user="test", started=datetime.now(timezone.utc), finished=finished
    )
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        await uow.steps.add(model.Step(name="step", state=step_state, deployment_id=deployment.id))
        await uow.commit()
    return deployment


async def test_delete_service_with_running_deployment_is_refused(bus, uow, service_in_db, publisher):
    deployment = await add_deployment(uow, service_in_db)

    with pytest.raises(model.ServiceHasActiveDeployment) as exc_info:
        await bus.handle(commands.DeleteService(service_id=service_in_db.id))

    assert exc_info.value.deployment_id == deployment.id
    assert exc_info.value.service_id == service_in_db.id
    async with uow:
        service = await uow.services.get(service_in_db.id)
        [kept] = await uow.deployments.get_by_service(service_in_db.id)
        [step] = await uow.steps.get_steps_by_deployment(deployment.id)
    assert service.name == service_in_db.name
    assert kept.id == deployment.id
    assert step.name == "step"
    assert publisher.events == []


async def test_delete_service_with_finished_deployment_cascades(bus, uow, service_in_db):
    deployment = await add_deployment(uow, service_in_db, finished=datetime.now(timezone.utc), step_state="success")

    await bus.handle(commands.DeleteService(service_id=service_in_db.id))

    async with uow:
        assert await uow.deployments.get_by_service(service_in_db.id) == []
        assert await uow.steps.get_steps_by_deployment(deployment.id) == []
        with pytest.raises(NoResultFound):
            await uow.services.get(service_in_db.id)


async def test_delete_service_with_stale_deployment_is_allowed(bus, uow, service_in_db):
    """Same rule as the single-flight check: a deployment older than its token no longer blocks."""
    deployment = await add_deployment(uow, service_in_db)
    async with uow:
        deployment.started = datetime.now(timezone.utc) - timedelta(days=2)
        await uow.deployments.add(deployment)
        await uow.commit()

    await bus.handle(commands.DeleteService(service_id=service_in_db.id))

    async with uow:
        assert await uow.deployments.get_by_service(service_in_db.id) == []


@pytest.mark.db("in_memory")
async def test_delete_service_guard_with_in_memory_repositories(bus, uow, service_in_db):
    deployment = await add_deployment(uow, service_in_db)

    with pytest.raises(model.ServiceHasActiveDeployment):
        await bus.handle(commands.DeleteService(service_id=service_in_db.id))

    async with uow:
        assert (await uow.services.get(service_in_db.id)).name == service_in_db.name
        assert [d.id for d in await uow.deployments.get_by_service(service_in_db.id)] == [deployment.id]


async def make_bus(publisher, services_filesystem):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
    uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
    await uow.connect()
    return await bootstrap(
        start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
    )


@patch("deploy.tasks.subprocess.Popen")
async def test_delete_racing_with_deployment_start_keeps_the_deployment(
    popen, database, publisher, services_filesystem, monkeypatch
):
    """
    The start holds the service lock and has not committed its deployment yet
    when the delete arrives. The delete has to wait for the start and then see
    the new deployment, instead of deleting the service underneath it.
    """
    setup_bus = await make_bus(publisher, services_filesystem)
    service = model.Service(name="delete-race", data={})
    async with setup_bus.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    service_id = service.id
    assert service_id is not None

    start_holds_lock = asyncio.Event()
    original = repository.SqlAlchemyDeploymentRepository.get_unfinished_by_service

    async def slow_get_unfinished_by_service(self, service_id):
        result = await original(self, service_id)
        if not start_holds_lock.is_set():
            # first caller is the start: it holds the service lock here
            start_holds_lock.set()
            await asyncio.sleep(0.5)
        return result

    monkeypatch.setattr(
        repository.SqlAlchemyDeploymentRepository, "get_unfinished_by_service", slow_get_unfinished_by_service
    )

    start_bus = await make_bus(publisher, services_filesystem)
    delete_bus = await make_bus(publisher, services_filesystem)
    try:
        start = asyncio.create_task(
            start_bus.handle(commands.StartDeployment(service_id=service_id, origin="test", user="test", context={}))
        )
        await asyncio.wait_for(start_holds_lock.wait(), timeout=10)
        with pytest.raises(model.ServiceHasActiveDeployment) as exc_info:
            await asyncio.wait_for(delete_bus.handle(commands.DeleteService(service_id=service_id)), timeout=30)
        await asyncio.wait_for(start, timeout=30)

        async with setup_bus.uow as uow:
            kept = await uow.services.get(service_id)
            [deployment] = await uow.deployments.get_by_service(service_id)
        assert kept.name == "delete-race"
        assert exc_info.value.deployment_id == deployment.id
        assert popen.call_count == 1
    finally:
        for bus in (start_bus, delete_bus, setup_bus):
            await bus.uow.close()
