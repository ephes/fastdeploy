import pytest

from httpx import AsyncClient

from deploy.domain import model


pytestmark = pytest.mark.asyncio


# test get_deployments endpoint


async def test_get_deployments_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_deployments"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_get_deployments_happy(app, deployment_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployments"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    deployment_from_api = model.Deployment(**result[0])
    assert deployment_from_api == deployment_in_db


# test get_deployment_details endpoint


async def test_get_deployment_details_no_such_deployment(app, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url="http://test") as client:
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
    async with AsyncClient(app=app, base_url="http://test") as client:
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
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_deployment_details", deployment_id=deployment.id), headers=headers
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["steps"]) > 0


# test finish_deployment endpoint


async def test_finish_deployment_invalid_access_token(app, valid_service_token_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url="http://test") as client:
        finish_deployment = app.url_path_for("finish_deployment")
        response = await client.put(finish_deployment, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


async def test_finish_deployment_happy(app, valid_deploy_token_in_db):
    headers = {"authorization": f"Bearer {valid_deploy_token_in_db}"}
    async with AsyncClient(app=app, base_url="http://test") as client:
        finish_deployment = app.url_path_for("finish_deployment")
        response = await client.put(finish_deployment, headers=headers)

    assert response.status_code == 200
    detail = response.json()["detail"]
    assert "finished" in detail
