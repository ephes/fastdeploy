import pytest

from httpx import AsyncClient

from ..auth import verify_access_token


@pytest.mark.asyncio
async def test_fetch_service_token_no_access_token(app, base_url, service_token):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(app.url_path_for("service_token"), json=service_token.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_fetch_service_token(app, base_url, service_token, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("service_token"),
            json=service_token.dict(),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    token = response.json()["service_token"]
    payload = verify_access_token(token)
    assert service_token.service.name == payload["service"]
    assert service_token.origin == payload["origin"]
