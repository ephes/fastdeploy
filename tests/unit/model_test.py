from datetime import datetime, timedelta, timezone

import pytest

from deploy.domain import model


pytestmark = pytest.mark.asyncio


@pytest.fixture
def deployment():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    return model.Deployment(service_id=1, origin="GitHub", user="foobar", started=started)


@pytest.fixture
def step():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    finished = started + timedelta(minutes=3)
    return model.Step(name="step from database", started=started, finished=finished, state="failure")


# test domain.model.Deployment.process_step


async def test_not_started_deployment_cannot_process_steps(deployment, step):
    deployment.started = None
    with pytest.raises(ValueError):
        await deployment.process_step(step)


async def test_finished_deployment_cannot_process_steps(deployment, step):
    deployment.finished = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        await deployment.process_step(step)


async def test_deployment_process_unknown_step(deployment):
    unknown_step = model.Step(id=1, name="Unknown step", deployment_id=deployment.id, state="success")
    modified_steps = deployment.process_step(unknown_step)
    assert unknown_step in modified_steps


async def test_deployment_process_known_running_step(deployment):
    known_step = model.Step(
        id=1, name="known step", started=datetime.now(timezone.utc), deployment_id=deployment.id, state="running"
    )
    finished_step = model.Step(**(known_step.dict() | {"state": "success"}))
    deployment.steps = [known_step]
    modified_steps = deployment.process_step(finished_step)
    assert [finished_step] == modified_steps
