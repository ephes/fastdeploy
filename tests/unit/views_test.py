from datetime import datetime, timedelta

import pytest

from deploy import views
from deploy.domain import model


pytestmark = pytest.mark.asyncio

# test views.get_steps_to_do_from_service


async def test_get_steps_to_do_from_service_returns_placeholder_step(service):
    steps = await views.get_steps_to_do_from_service(service)
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


async def test_get_steps_to_do_from_service_has_steps_in_data(service):
    step = model.Step(id=1, name="Step 1")
    service.data = {"steps": [step.dict()]}
    steps = await views.get_steps_to_do_from_service(service)
    assert [step] == steps


async def test_get_steps_to_do_from_service_steps_from_last_deployment(uow, service_in_db):
    service = service_in_db
    started = datetime.utcnow() - timedelta(days=1)
    finished = started + timedelta(minutes=3)
    deployment = model.Deployment(
        service_id=service.id, origin="GitHub", user="foobar", started=started, finished=finished
    )
    step = model.Step(name="step from database", started=started, finished=finished, state="success")
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        step.deployment_id = deployment.id
        await uow.steps.add(step)
        await uow.commit()

    steps = await views.get_steps_to_do_from_service(service, uow=uow)
    assert steps[0].name == "step from database"
