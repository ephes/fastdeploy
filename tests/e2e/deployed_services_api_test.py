from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token
from deploy.domain import model

pytestmark = pytest.mark.asyncio


# test list_deployed_services endpoint


async def test_list_deployed_services_without_authentication(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("list_deployed_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def valid_config_token(service):
    """Valid config token."""
    return create_access_token({"type": "config"}, timedelta(minutes=5))


async def test_list_deployed_services_happy(app, deployed_service_in_db, valid_config_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("list_deployed_services"),
            headers={"authorization": f"Bearer {valid_config_token}"},
        )

    assert response.status_code == 200
    result = response.json()
    deployed_service_from_api = model.DeployedService(**result[0])
    assert deployed_service_from_api == deployed_service_in_db
