from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio

from deploy import views
from deploy.domain import commands, events, model


pytestmark = pytest.mark.asyncio


async def test_last_successful_id_multiple_deployments(uow, service_in_db):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    finished = started + timedelta(minutes=1)
    params = {
        "service_id": service_in_db.id,
        "origin": "github",
        "user": "fastdeploy",
        "started": started,
        "finished": finished,
        "context": {},
    }
    d1 = model.Deployment(**params)
    params["started"] = finished
    params["finished"] = finished + timedelta(minutes=1)
    d2 = model.Deployment(**params)
    async with uow:
        await uow.deployments.add(d1)
        await uow.deployments.add(d2)
        await uow.commit()

    step1 = model.Step(
        name="first successful step", deployment_id=d1.id, state="success", started=started, finished=finished
    )
    step2 = model.Step(
        name="second successful step", deployment_id=d2.id, state="success", started=finished, finished=d2.finished
    )
    async with uow:
        await uow.steps.add(step1)
        await uow.steps.add(step2)
        await uow.commit()

    steps = await views.get_steps_from_last_deployment(service_in_db, uow)
    assert steps[0].deployment_id == d2.id


@pytest_asyncio.fixture()
async def service_with_steps(uow, service_in_db):
    """Need two steps, because the first one is always set to 'running'"""
    service_in_db.data = {
        "steps": [{"name": "step1"}, {"name": "step2"}],
    }
    async with uow:
        await uow.services.add(service_in_db)
        await uow.commit()
    return service_in_db


@pytest.fixture
def deployment_started_handler(bus):
    # register deployment started handler to get the deployment_id
    class DeploymentStartedHandler:
        event: events.DeploymentStarted

        async def __call__(self, event: events.DeploymentStarted):
            self.event = event

    handle_deployment_started = DeploymentStartedHandler()
    bus.event_handlers[events.DeploymentStarted].append(handle_deployment_started)
    return handle_deployment_started


async def process_steps(bus, deployment_id):
    async with bus.uow as uow:
        steps = [s for s, in await uow.steps.get_steps_from_deployment(deployment_id)]
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    for step in steps:
        started = started + timedelta(minutes=1)
        finished = started + timedelta(minutes=1)
        cmd = commands.ProcessStep(
            deployment_id=deployment_id,
            name=step.name,
            state="success",
            started=started,
            finished=finished,
            message="",
        )
        await bus.handle(cmd)


@patch("deploy.tasks.subprocess.Popen")
async def test_two_deployments(popen, bus, service_with_steps, deployment_started_handler):
    """
    There was a bug where the steps first deployment get assigned to the
    second deployment. Make sure it wont happen again.
    """
    service = service_with_steps
    # deployment parameters
    params = {
        "service_id": service.id,
        "origin": "github",
        "user": "fastdeploy",
        "context": {},
    }
    # start first deployment
    cmd = commands.StartDeployment(**params)
    await bus.handle(cmd)
    first_deployment_id = deployment_started_handler.event.id

    # process steps of first deployment
    await process_steps(bus, first_deployment_id)

    # finish first deployment
    cmd = commands.FinishDeployment(deployment_id=first_deployment_id)
    await bus.handle(cmd)

    # start second deployment
    cmd = commands.StartDeployment(**params)
    await bus.handle(cmd)
    second_deployment_id = deployment_started_handler.event.id

    async with bus.uow as uow:
        steps = [s for s, in await uow.steps.get_steps_from_deployment(second_deployment_id)]
        print("steps state:", steps[0].state)

    # process steps of second deployment
    await process_steps(bus, second_deployment_id)

    # finish second deployment
    cmd = commands.FinishDeployment(deployment_id=second_deployment_id)
    await bus.handle(cmd)

    # make sure step from first deployment is not assigned to second deployment
    async with bus.uow as uow:
        first_steps = [s for s, in await uow.steps.get_steps_from_deployment(first_deployment_id)]
        assert len(first_steps) > 0

    # make only planned steps were assigned to second deployment
    async with bus.uow as uow:
        second_steps = [s for s, in await uow.steps.get_steps_from_deployment(second_deployment_id)]
        assert len(second_steps) == len(service.data["steps"])


async def test_steps_removed_after_finish(bus, deployment_in_db):
    step1 = model.Step(name="a pending step", deployment_id=deployment_in_db.id, state="pending")
    step2 = model.Step(name="a pending step", deployment_id=deployment_in_db.id, state="running")
    async with bus.uow as uow:
        await uow.steps.add(step1)
        await uow.steps.add(step2)
        await uow.commit()

    cmd = commands.FinishDeployment(deployment_id=deployment_in_db.id)
    await bus.handle(cmd)

    async with bus.uow as uow:
        steps = await uow.steps.get_steps_from_deployment(deployment_in_db.id)
        assert len(steps) == 0