import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_task_no_access_token(app, base_url, task):
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("tasks")
        print("test_url: ", test_url)
        response = await client.post(test_url, data=task.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
