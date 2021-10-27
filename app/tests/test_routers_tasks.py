import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_taskresult_by_user_no_access_token(app, base_url, taskresult):
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("task_by_user")
        response = await client.post(test_url, data=taskresult)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_taskresult_by_service_no_access_token(app, base_url, taskresult):
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("task_by_service")
        response = await client.post(test_url, data=taskresult)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
