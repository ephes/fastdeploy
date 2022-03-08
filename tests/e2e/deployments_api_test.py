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
