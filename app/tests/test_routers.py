import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_deploy_by_user(app, base_url, valid_access_token_in_db, service):
    headers = {"authorization": f"Bearer {valid_access_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(f"/deployments/deploy-by-user/{service.id}", headers=headers)

    assert response.status_code == 401
    print("response: ", response.json())
    assert response.json() == {"detail": "Not authenticated"}
    assert False
