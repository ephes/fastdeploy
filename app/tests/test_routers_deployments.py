from unittest.mock import patch

import pytest
import pytest_asyncio

from httpx import AsyncClient

from app.auth import token_to_payload
from app.models import Deployment, Service, Step


@pytest.mark.asyncio
async def test_get_deployments_without_authentication(app, base_url):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("get_deployments"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_deployments(app, base_url, deployment_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    deployment_from_api = result[0]
    assert deployment_from_api["id"] == deployment_in_db.id


@pytest.mark.asyncio
async def test_deploy_no_access_token(app, base_url):
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("start_deployment")
            response = await client.post(test_url)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_deploy_invalid_access_token(app, base_url, invalid_service_token):
    headers = {"authorization": f"Bearer {invalid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("start_deployment")
            response = await client.post(test_url, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_service_not_found(app, base_url, valid_service_token):
    headers = {"authorization": f"Bearer {valid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("start_deployment")
        response = await client.post(test_url, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_service_with_context(app, base_url, valid_service_token_in_db):
    my_context = {"env": {"foobar": "barfoo"}}
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("start_deployment")
            response = await client.post(test_url, headers=headers, json=my_context)

    assert response.status_code == 200
    deployment_from_api = response.json()
    assert "id" in deployment_from_api
    assert deployment_from_api["context"] == my_context


@pytest.mark.asyncio
async def test_deploy_service(app, base_url, repository, handler, valid_service_token_in_db, service_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("start_deployment")
            response = await client.post(test_url, headers=headers)

    assert response.status_code == 200
    deployment_from_api = response.json()
    assert "id" in deployment_from_api

    # make sure added deployment was dispatched to event handlers
    assert handler.events[-3].type == "deployment"
    assert handler.last_event.type == "step"  # there's at least a default step added after deployment

    # make sure deployment was added to service in database
    deployments_by_service = await repository.get_deployments_by_service_id(service_in_db.id)
    assert len(deployments_by_service) == 1
    assert deployment_from_api["id"] == deployments_by_service[0].id


@pytest.mark.asyncio
async def test_finish_deploy_invalid_access_token(app, base_url, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("finish_deployment")
        response = await client.put(test_url, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_finish_deploy(app, base_url, valid_deploy_token_in_db):
    headers = {"authorization": f"Bearer {valid_deploy_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("finish_deployment")
        response = await client.put(test_url, headers=headers)

    assert response.status_code == 200
    deployment_from_api = response.json()
    assert "id" in deployment_from_api

    assert "T" in deployment_from_api["finished"]


@pytest.mark.asyncio
async def test_get_deployment_details_no_such_deployment(app, base_url, deployment_in_db, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("get_deployment_details", deployment_id=666), headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Deployment does not exist"}


@pytest_asyncio.fixture
async def deployment_from_other_service(repository):
    service = Service(name="fastdeploytest_other", data={"foo": "bar"})
    service = await repository.add_service(service)
    deployment = Deployment(service_id=service.id, origin="github", user="fastdeploy")
    deployment, _ = await repository.add_deployment(deployment, [])
    return deployment


@pytest.mark.asyncio
async def test_get_deployment_details_wrong_service(
    app, base_url, repository, deployment_from_other_service, valid_service_token_in_db
):
    service = await repository.get_service_by_id(deployment_from_other_service.service_id)
    payload = await token_to_payload(valid_service_token_in_db)
    assert service.name != payload["service"]
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment_from_other_service.id), headers=headers
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Wrong service token"}


@pytest_asyncio.fixture
async def deployment_with_steps(repository, deployment_in_db):
    step = Step(name="step1", state="success", deployment_id=deployment_in_db.id)
    await repository.add_step(step)
    return deployment_in_db


@pytest.mark.asyncio
async def test_get_deployment_details(app, base_url, deployment_with_steps, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment_with_steps.id), headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["steps"]) > 0
