import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_services_without_authentication(app, base_url):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("get_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_services(app, base_url, service_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    service_from_api = result[0]
    assert service_from_api["name"] == service_in_db.name
