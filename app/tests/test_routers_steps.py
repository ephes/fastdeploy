import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_step_no_access_token(app, base_url, step):
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("steps")
        response = await client.post(test_url, data=step.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_post_step_invalid_access_token(app, base_url, step, invalid_deploy_token):
    headers = {"authorization": f"Bearer {invalid_deploy_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("steps")
        response = await client.post(test_url, data=step.dict(), headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_post_step_deployment_not_found(app, base_url, step, valid_deploy_token, cleanup_database_after_test):
    headers = {"authorization": f"Bearer {valid_deploy_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("steps")
        response = await client.post(test_url, data=step.dict(), headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_post_step_deployment_found(app, base_url, step, valid_deploy_token_in_db, deployment_in_db):
    step.deployment_id = deployment_in_db.id
    headers = {"authorization": f"Bearer {valid_deploy_token_in_db}"}
    data = {
        "step": step.dict(),
        "deployment_id": 1,
    }
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("steps")
        response = await client.post(test_url, data=data, headers=headers)

    print("response: ", response.json())
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert False
