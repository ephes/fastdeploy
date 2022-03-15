import json

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from httpx import AsyncClient

from deploy.auth import create_access_token
from deploy.domain import events, model
from deploy.entrypoints.helper_models import StepResult


pytestmark = pytest.mark.asyncio

# test process_step_result endpoint


@pytest.fixture
def step():
    return model.Step(name="foo bar baz")


async def test_process_step_no_access_token(app, step):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(app.url_path_for("process_step_result"), json=step.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def invalid_deploy_token():
    return create_access_token({"type": "deployment", "deployment": 1}, timedelta(minutes=-5))


async def test_process_step_invalid_access_token(app, step, invalid_deploy_token):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.dict(),
            headers={"authorization": f"Bearer {invalid_deploy_token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.fixture
def valid_deploy_token(deployment):
    data = {"type": "deployment", "deployment": deployment.id}
    return create_access_token(data, timedelta(minutes=5))


async def test_process_step_deployment_not_found(app, step, valid_deploy_token):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.dict(),
            headers={"authorization": f"Bearer {valid_deploy_token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.fixture
def valid_deploy_token_in_db(deployment_in_db):
    data = {"type": "deployment", "deployment": deployment_in_db.id}
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def step_result(deployment_in_db):
    return StepResult(
        name="just a small step",
        deployment_id=deployment_in_db.id,
        state="success",
        started=datetime.now(timezone.utc) - timedelta(minutes=3),
        finished=datetime.now(timezone.utc) - timedelta(minutes=2),
        message="",
    )


async def test_process_step_happy(app, uow, step_result, publisher, valid_deploy_token_in_db, deployment_in_db):
    print("step: ", step_result)
    deployment_in_db.started = datetime.now(timezone.utc)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=json.loads(step_result.json()),
            headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
        )

    # make sure step was processed
    assert response.status_code == 200
    result = response.json()
    assert "processed" in result["detail"]

    # make sure processed step was dispatched to event handlers
    channel, step_processed = publisher.events[0]
    assert channel == "broadcast"
    assert isinstance(step_processed, events.StepProcessed)
    assert step_processed.name == step_result.name

    # make sure step was persisted
    async with uow:
        [[step]] = await uow.steps.list()
        assert step.name == step_result.name


# test get_steps_by_deployment endpoint


async def test_get_steps_by_deployment_no_access_token(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_steps_by_deployment"), params={"deployment_id": 1})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest_asyncio.fixture()
async def step_in_db(uow, deployment_in_db):
    step = model.Step(name="foo bar baz", deployment_id=deployment_in_db.id)
    async with uow:
        await uow.steps.add(step)
        await uow.commit()
    return step


async def test_get_steps_by_deployment_happy(app, step_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_steps_by_deployment"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            params={"deployment_id": step_in_db.deployment_id},
        )

    assert response.status_code == 200
    steps_by_deployment = response.json()
    assert steps_by_deployment[0]["id"] == step_in_db.id
    assert "deployment_id" in steps_by_deployment[0]
