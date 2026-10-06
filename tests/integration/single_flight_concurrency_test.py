"""
Concurrent deployment starts for the same service against the real database.

Each start runs on its own connection/transaction (like two concurrent API
requests), so this exercises the database-level per-service lock rather than
the test suite's shared rolling-back session.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.adapters import repository
from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.domain import commands, model
from deploy.service_layer import unit_of_work

pytestmark = pytest.mark.asyncio

CONCURRENT_STARTS = 5


async def make_bus(publisher, services_filesystem):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
    uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
    await uow.connect()
    return await bootstrap(
        start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
    )


@pytest.fixture
def widen_check_insert_window(monkeypatch):
    """
    Yield to the event loop between "look for unfinished deployments" and
    "insert the new deployment" so that, without a lock, every concurrent
    start would pass the check before any of them inserts.
    """
    original = repository.SqlAlchemyDeploymentRepository.get_unfinished_by_service

    async def slow_get_unfinished_by_service(self, service_id):
        result = await original(self, service_id)
        await asyncio.sleep(0.2)
        return result

    monkeypatch.setattr(
        repository.SqlAlchemyDeploymentRepository, "get_unfinished_by_service", slow_get_unfinished_by_service
    )


@patch("deploy.tasks.subprocess.Popen")
async def test_concurrent_starts_yield_exactly_one_deployment(
    popen, database, publisher, services_filesystem, widen_check_insert_window
):
    setup_bus = await make_bus(publisher, services_filesystem)
    service = model.Service(name="single-flight", data={})
    async with setup_bus.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    service_id = service.id
    assert service_id is not None

    buses = [await make_bus(publisher, services_filesystem) for _ in range(CONCURRENT_STARTS)]
    cmd = commands.StartDeployment(service_id=service_id, origin="test", user="test", context={})
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(bus.handle(cmd) for bus in buses), return_exceptions=True), timeout=30
        )
    finally:
        for bus in buses:
            await bus.uow.close()

    successes = [r for r in results if r is None]
    conflicts = [r for r in results if isinstance(r, model.DeploymentAlreadyRunning)]
    assert len(successes) == 1, results
    assert len(conflicts) == CONCURRENT_STARTS - 1, results
    assert popen.call_count == 1

    async with setup_bus.uow as uow:
        deployments = await uow.deployments.get_by_service(service_id)
    try:
        assert len(deployments) == 1
        assert {c.deployment_id for c in conflicts} == {deployments[0].id}
    finally:
        await setup_bus.uow.close()
