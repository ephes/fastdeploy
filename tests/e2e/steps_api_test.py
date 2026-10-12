import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token
from deploy.domain import events, model
from deploy.entrypoints.helper_models import (
    MAX_STEP_MESSAGE_LENGTH,
    MAX_STEP_NAME_LENGTH,
    MAX_STEP_STATE_LENGTH,
    StepResult,
)
from deploy.tasks import MAX_STEP_MESSAGE_SIZE

pytestmark = pytest.mark.asyncio

# test process_step_result endpoint


@pytest.fixture
def step():
    return model.Step(name="foo bar baz")


async def test_process_step_no_access_token(app, step):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(app.url_path_for("process_step_result"), json=step.model_dump())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def invalid_deploy_token():
    return create_access_token({"type": "deployment", "deployment": 1}, timedelta(minutes=-5))


async def test_process_step_invalid_access_token(app, step, invalid_deploy_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.model_dump(),
            headers={"authorization": f"Bearer {invalid_deploy_token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.fixture
def valid_deploy_token(deployment):
    data = {"type": "deployment", "deployment": deployment.id}
    return create_access_token(data, timedelta(minutes=5))


async def test_process_step_deployment_not_found(app, step, valid_deploy_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.model_dump(),
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
    deployment_in_db.started = datetime.now(timezone.utc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=json.loads(step_result.model_dump_json()),
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
        [step] = await uow.steps.list()
        assert step.name == step_result.name


async def test_process_step_repeated_report(app, uow, step_result, publisher, valid_deploy_token_in_db):
    """A retried report (lost response) is accepted again without a second step or event."""
    payload = json.loads(step_result.model_dump_json())
    headers = {"authorization": f"Bearer {valid_deploy_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(app.url_path_for("process_step_result"), json=payload, headers=headers)
        events_after_first_report = len(publisher.events)
        second = await client.post(app.url_path_for("process_step_result"), json=payload, headers=headers)
        conflicting = await client.post(
            app.url_path_for("process_step_result"), json=payload | {"state": "failure"}, headers=headers
        )

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == first.json()
    assert conflicting.status_code == 409
    assert conflicting.json() == {"detail": "Step was already reported with a different result"}
    assert len(publisher.events) == events_after_first_report
    async with uow:
        [step] = await uow.steps.list()
        assert (step.name, step.state) == (step_result.name, "success")


@pytest.mark.parametrize(
    "field, limit",
    [("message", MAX_STEP_MESSAGE_LENGTH), ("name", MAX_STEP_NAME_LENGTH), ("state", MAX_STEP_STATE_LENGTH)],
)
async def test_process_step_rejects_oversized_fields(
    field, limit, app, uow, step_result, publisher, valid_deploy_token_in_db
):
    payload = json.loads(step_result.model_dump_json()) | {field: "x" * (limit + 1)}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=payload,
            headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
        )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", field]
    assert error["type"] == "string_too_long"
    assert f"at most {limit} characters" in error["msg"]
    # nothing was stored or broadcast
    assert publisher.events == []
    async with uow:
        assert await uow.steps.list() == []


async def test_process_step_accepts_message_at_the_limit(app, uow, step_result, valid_deploy_token_in_db):
    """The deploy task cuts messages to this length, they must still be accepted."""
    assert MAX_STEP_MESSAGE_LENGTH == MAX_STEP_MESSAGE_SIZE
    payload = json.loads(step_result.model_dump_json()) | {"message": "x" * MAX_STEP_MESSAGE_LENGTH}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=payload,
            headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
        )

    assert response.status_code == 200
    async with uow:
        [step] = await uow.steps.list()
        assert len(step.message) == MAX_STEP_MESSAGE_LENGTH


# test get_steps_by_deployment endpoint


async def test_get_steps_by_deployment_no_access_token(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_steps_by_deployment"), params={"deployment_id": 1})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest_asyncio.fixture(loop_scope="function")
async def step_in_db(uow, deployment_in_db):
    step = model.Step(name="foo bar baz", deployment_id=deployment_in_db.id)
    async with uow:
        await uow.steps.add(step)
        await uow.commit()
    return step


async def test_get_steps_by_deployment_happy(app, step_in_db, valid_access_token_in_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_steps_by_deployment"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            params={"deployment_id": step_in_db.deployment_id},
        )

    assert response.status_code == 200
    steps_by_deployment = response.json()
    assert steps_by_deployment[0]["id"] == step_in_db.id
    assert "deployment_id" in steps_by_deployment[0]


async def test_get_steps_by_deployment_unknown_deployment(app, valid_access_token_in_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_steps_by_deployment"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            params={"deployment_id": 666},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Deployment not found"}
