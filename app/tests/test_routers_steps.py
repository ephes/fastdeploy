import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_step_no_access_token(app, base_url, step):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(app.url_path_for("steps"), json=step.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_add_step_invalid_access_token(app, base_url, step, invalid_deploy_token):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("steps"), json=step.dict(), headers={"authorization": f"Bearer {invalid_deploy_token}"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_add_step_deployment_not_found(app, base_url, step, valid_deploy_token, cleanup_database_after_test):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("steps"), json=step.dict(), headers={"authorization": f"Bearer {valid_deploy_token}"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_add_step(app, base_url, step, valid_deploy_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("steps"),
            json=step.dict(),
            headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
        )

    assert response.status_code == 200
    assert response.json() == {"received": True}
