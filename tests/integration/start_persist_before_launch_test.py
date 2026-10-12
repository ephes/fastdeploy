"""
The detached deploy task may report its first step as soon as it exists. The
report runs on its own connection (like the API request of the task), so it
only sees what the start has committed before launching the task.
"""

import asyncio
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.domain import commands, model
from deploy.service_layer import unit_of_work

pytestmark = pytest.mark.asyncio


async def make_bus(publisher, services_filesystem):
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
    uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
    await uow.connect()
    return await bootstrap(
        start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
    )


async def test_immediate_first_report_finds_committed_planned_steps(database, publisher, services_filesystem):
    setup_bus = await make_bus(publisher, services_filesystem)
    service = model.Service(name="fast-child", data={"steps": [{"name": "step1"}, {"name": "step2"}]})
    async with setup_bus.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    assert service.id is not None

    seen_by_task: list[list[tuple[str, str]]] = []
    errors: list[BaseException] = []

    async def report_first_step(deployment_id):
        bus = await make_bus(publisher, services_filesystem)
        try:
            async with bus.uow as uow:
                steps = await uow.steps.get_steps_by_deployment(deployment_id)
                seen_by_task.append(sorted((step.name, step.state) for step in steps))
            now = datetime.now(timezone.utc)
            await bus.handle(
                commands.ProcessStep(
                    deployment_id=deployment_id, name="step1", state="success", started=now, finished=now, message=""
                )
            )
        finally:
            await bus.uow.close()

    def fast_deploy_task(environment):
        """Stands in for the detached process: it reports before the launch returns."""
        from deploy.auth import token_to_payload

        deployment_id = token_to_payload(environment["ACCESS_TOKEN"])["deployment"]

        def run():
            try:
                asyncio.run(report_first_step(deployment_id))
            except BaseException as e:
                errors.append(e)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=30)
        assert not thread.is_alive()

    start_bus = await make_bus(publisher, services_filesystem)
    try:
        with patch("deploy.tasks.run_deploy", fast_deploy_task):
            await start_bus.handle(
                commands.StartDeployment(service_id=service.id, origin="test", user="test", context={})
            )
    finally:
        await start_bus.uow.close()

    try:
        assert errors == []
        assert seen_by_task == [[("step1", "running"), ("step2", "pending")]]
        async with setup_bus.uow as uow:
            [deployment] = await uow.deployments.get_by_service(service.id)
            steps = await uow.steps.get_steps_by_deployment(deployment.id)
        assert sorted((step.name, step.state) for step in steps) == [("step1", "success"), ("step2", "running")]
    finally:
        await setup_bus.uow.close()
