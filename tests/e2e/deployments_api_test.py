from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token
from deploy.domain import events, model

pytestmark = pytest.mark.asyncio


# test get_deployments endpoint


async def test_get_deployments_without_authentication(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_deployments"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_get_deployments_happy(app, deployment_in_db, valid_access_token_in_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    deployment_from_api = model.Deployment(**result[0])
    assert deployment_from_api == deployment_in_db


@pytest.mark.db("in_memory")
async def test_get_deployments_reconciles_orphaned_unfinished(app, uow, service_in_db, valid_access_token_in_db):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(
            name="finished step",
            deployment_id=deployment.id,
            state="success",
            started=started,
            finished=started,
            message="ok",
        )
        await uow.steps.add(step)
        await uow.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    deployments = response.json()
    reconciled = next(d for d in deployments if d["id"] == deployment.id)
    assert reconciled["finished"] is not None

    async with uow:
        [updated] = await uow.deployments.get(deployment.id)
    assert updated.finished is not None


@pytest.mark.db("in_memory")
async def test_get_deployments_does_not_reconcile_running(app, uow, service_in_db, valid_access_token_in_db):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(
            name="running step",
            deployment_id=deployment.id,
            state="running",
            started=started,
            finished=None,
            message="",
        )
        await uow.steps.add(step)
        await uow.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    deployments = response.json()
    running = next(d for d in deployments if d["id"] == deployment.id)
    assert running["finished"] is None

    async with uow:
        [updated] = await uow.deployments.get(deployment.id)
    assert updated.finished is None


# test get_deployment_details endpoint


async def test_get_deployment_details_no_such_deployment(app, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_deployment_details", deployment_id=666), headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Deployment not found"}


async def test_get_deployment_details_wrong_service(app, uow, valid_service_token_in_db):
    service = model.Service(name="another service")
    async with uow:
        await uow.services.add(service)
        await uow.commit()
        assert isinstance(service.id, int)
        deployment = model.Deployment(service_id=service.id, origin="frontend", user="asdf")
        await uow.deployments.add(deployment)
        await uow.commit()

    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment.id), headers=headers
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Wrong service token"}


async def test_get_deployment_details_happy(app, uow, service, valid_service_token_in_db):
    async with uow:
        deployment = model.Deployment(service_id=service.id, origin="frontend", user="asdf")
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(name="step of deployment", deployment_id=deployment.id, state="running", message="")
        await uow.steps.add(step)
        await uow.commit()

    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment.id), headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["steps"]) > 0


@pytest.mark.db("in_memory")
async def test_get_deployment_details_reconciles_orphaned_unfinished(
    app, uow, service_in_db, valid_service_token_in_db
):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(
            name="finished step",
            deployment_id=deployment.id,
            state="success",
            started=started,
            finished=started,
            message="ok",
        )
        await uow.steps.add(step)
        await uow.commit()

    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment.id), headers=headers
        )

    assert response.status_code == 200
    assert response.json()["finished"] is not None

    async with uow:
        [updated] = await uow.deployments.get(deployment.id)
    assert updated.finished is not None


@pytest.mark.db("in_memory")
async def test_get_deployment_details_does_not_reconcile_brand_new_without_steps(
    app, uow, service_in_db, valid_service_token_in_db
):
    started = datetime.now(timezone.utc)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()

    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment.id), headers=headers
        )

    assert response.status_code == 200
    assert response.json()["finished"] is None


@pytest.mark.db("in_memory")
async def test_get_deployments_does_not_reconcile_brand_new_without_steps(
    app, uow, service_in_db, valid_access_token_in_db
):
    started = datetime.now(timezone.utc)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    deployments = response.json()
    fresh = next(d for d in deployments if d["id"] == deployment.id)
    assert fresh["finished"] is None


@pytest.mark.db("in_memory")
async def test_get_deployments_reconciles_old_without_steps(
    app, uow, service_in_db, valid_access_token_in_db
):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with uow:
        deployment = model.Deployment(
            service_id=service_in_db.id,
            origin="frontend",
            user="asdf",
            started=started,
            finished=None,
        )
        await uow.deployments.add(deployment)
        await uow.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    deployments = response.json()
    reconciled = next(d for d in deployments if d["id"] == deployment.id)
    assert reconciled["finished"] is not None

# test finish_deployment endpoint


async def test_finish_deployment_invalid_access_token(app, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        finish_deployment = app.url_path_for("finish_deployment")
        response = await client.put(finish_deployment, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


async def test_finish_deployment_happy(app, valid_deploy_token_in_db):
    headers = {"authorization": f"Bearer {valid_deploy_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        finish_deployment = app.url_path_for("finish_deployment")
        response = await client.put(finish_deployment, headers=headers)

    assert response.status_code == 200
    detail = response.json()["detail"]
    assert "finished" in detail


# test start_deployment endpoint


async def test_deploy_no_access_token(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_deployment = app.url_path_for("start_deployment")
        response = await client.post(start_deployment)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def invalid_service_token(service):
    return create_access_token(
        {"type": "service", "user": "foobar", "origin": "GitHub", "service": service.name}, timedelta(minutes=-5)
    )


async def test_deploy_invalid_access_token(app, invalid_service_token):
    headers = {"authorization": f"Bearer {invalid_service_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_deployment = app.url_path_for("start_deployment")
        response = await client.post(start_deployment, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.fixture
def valid_service_token(service):
    """Valid service token, but service is not in database."""
    return create_access_token({"type": "service", "service": service.name}, timedelta(minutes=5))


async def test_deploy_service_not_found(app, valid_service_token):
    headers = {"authorization": f"Bearer {valid_service_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_deployment = app.url_path_for("start_deployment")
        response = await client.post(start_deployment, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@patch("deploy.tasks.subprocess.Popen")
async def test_deploy_service_with_context(popen, app, valid_service_token_in_db):
    my_context = {"env": {"foobar": "barfoo"}}
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_deployment = app.url_path_for("start_deployment")
        response = await client.post(start_deployment, headers=headers, json=my_context)

    # assert subprocess.Popen was called correctly
    assert popen.call_args.args[0][-1] == "deploy.tasks"
    # Context is now passed via secure config file, not environment
    # Check that DEPLOY_CONFIG_FILE is in environment instead of CONTEXT
    assert "DEPLOY_CONFIG_FILE" in popen.call_args.kwargs["env"]
    assert "CONTEXT" not in popen.call_args.kwargs["env"]  # Should not be in env for security

    # assert response is correct
    assert response.status_code == 200
    deployment_from_api = response.json()
    assert "id" in deployment_from_api
    assert deployment_from_api["context"] == my_context


@patch("deploy.tasks.subprocess.Popen")
async def test_deploy_service_happy(popen, app, uow, publisher, valid_service_token_in_db, service_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_deployment = app.url_path_for("start_deployment")
        response = await client.post(start_deployment, headers=headers)

    print("response.content: ", response.content)
    assert response.status_code == 200
    deployment_from_api = response.json()
    assert "id" in deployment_from_api

    # make sure added deployment was dispatched to event handlers
    channel, deployment_started = publisher.events[0]
    assert channel == "broadcast"
    assert isinstance(deployment_started, events.DeploymentStarted)
    assert deployment_started.service_id == service_in_db.id

    # make sure deployment was added to service in database
    async with uow:
        [deployment] = await uow.deployments.get(deployment_from_api["id"])
    assert deployment.service_id == service_in_db.id
