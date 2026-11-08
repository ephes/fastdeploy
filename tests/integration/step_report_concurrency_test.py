"""Real handler races; PostgreSQL confirms the second connection is blocked."""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from deploy.adapters import repository
from deploy.domain import commands, events, model

pytestmark = pytest.mark.asyncio


async def seed(bus):
    now = datetime.now(timezone.utc)
    service = model.Service(name="report-race", data={})
    async with bus.uow as uow:
        await uow.services.add(service)
        await uow.flush()
        deployment = model.Deployment(service_id=service.id, origin="test", user="test", started=now)
        await uow.deployments.add(deployment)
        await uow.flush()
        await uow.steps.add(model.Step(name="final", state="running", deployment_id=deployment.id))
        await uow.commit()
    return deployment.id, now


async def run_locked_pair(database, monkeypatch, first, first_command, second, second_command):
    first_pid = await first.uow.connection.scalar(text("select pg_backend_pid()"))
    second_pid = await second.uow.connection.scalar(text("select pg_backend_pid()"))
    await first.uow.connection.rollback()
    await second.uow.connection.rollback()
    acquired, release = asyncio.Event(), asyncio.Event()
    original = repository.SqlAlchemyDeploymentRepository.get_for_update

    async def hold_first(self, deployment_id):
        deployment = await original(self, deployment_id)
        if self.session is first.uow.session:
            acquired.set()
            await release.wait()
        return deployment

    monkeypatch.setattr(repository.SqlAlchemyDeploymentRepository, "get_for_update", hold_first)
    tasks = [asyncio.create_task(first.handle(first_command))]
    try:
        await asyncio.wait_for(acquired.wait(), 5)
        tasks.append(asyncio.create_task(second.handle(second_command)))

        async def wait_for_block():
            async with database.connect() as observer:
                while True:
                    blockers = await observer.scalar(text("select pg_blocking_pids(:pid)"), {"pid": second_pid})
                    if first_pid in blockers:
                        break
                    assert not tasks[1].done(), "second writer bypassed the deployment lock"
                    await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_block(), 5)
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
    return results


@pytest.mark.parametrize("second_state", ["success", "failure"])
async def test_equal_and_conflicting_reports(database, independent_bus, publisher, monkeypatch, second_state):
    setup, first, second = [await independent_bus() for _ in range(3)]
    deployment_id, now = await seed(setup)
    report = {"deployment_id": deployment_id, "name": "final", "started": now, "finished": now, "message": "synthetic"}
    results = await run_locked_pair(
        database,
        monkeypatch,
        first,
        commands.ProcessStep(state="success", **report),
        second,
        commands.ProcessStep(state=second_state, **report),
    )
    assert results[0] is None
    if second_state == "success":
        assert results[1] is None
    else:
        assert isinstance(results[1], model.StepReportConflict)
    async with setup.uow as uow:
        steps = await uow.steps.get_steps_by_deployment(deployment_id)
        deployment = await uow.deployments.get(deployment_id)
    assert [(s.name, s.state, s.message) for s in steps] == [("final", "success", "synthetic")]
    assert deployment.finished is None
    assert sum(isinstance(event, events.StepProcessed) for _, event in publisher.events) == 1
    assert not any(isinstance(event, events.DeploymentFinished) for _, event in publisher.events)
