from unittest.mock import AsyncMock, patch

import pytest

from httpx import AsyncClient

from ..models import Step


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
async def test_add_step_deployment_not_found(app, base_url, step, valid_deploy_token):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("steps"), json=step.dict(), headers={"authorization": f"Bearer {valid_deploy_token}"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_add_step(app, base_url, repository, step, valid_deploy_token_in_db, deployment_in_db):
    connection_manager = AsyncMock()
    with patch("app.routers.steps.connection_manager", new=connection_manager):
        async with AsyncClient(app=app, base_url=base_url) as client:
            response = await client.post(
                app.url_path_for("steps"),
                json=step.dict(),
                headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
            )

    assert response.status_code == 200
    actual_step = response.json()
    assert actual_step["id"] > 0
    assert actual_step["name"] == step.name

    # make sure added step was broadcast to websockets
    connection_manager.broadcast.assert_called()

    # make sure step was added to deployment in database
    steps_from_db = repository.get_steps_by_name(step.name)
    step_from_db = steps_from_db[0]
    assert step_from_db.id > 0
    assert step.name == step_from_db.name


@pytest.mark.asyncio
async def test_update_step_wrong_deployment(
    app, base_url, step_in_db, valid_different_deploy_token_in_db, deployment_in_db
):
    step = step_in_db
    step.deployment_id += 10
    step.name = f"{step.name} updated"
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.put(
            app.url_path_for("step_update", step_id=step.id),
            content=step.json().encode("utf8"),
            headers={"authorization": f"Bearer {valid_different_deploy_token_in_db}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_update_step(app, base_url, repository, step_in_db, valid_deploy_token_in_db, deployment_in_db):
    step = step_in_db
    step.name = f"{step.name} updated"
    connection_manager = AsyncMock()
    with patch("app.routers.steps.connection_manager", new=connection_manager):
        async with AsyncClient(app=app, base_url=base_url) as client:
            response = await client.put(
                app.url_path_for("step_update", step_id=step.id),
                content=step.json().encode("utf8"),
                headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
            )

    assert response.status_code == 200
    assert Step(**response.json()) == step.dict()

    # make sure update was broadcast to websockets
    connection_manager.broadcast.assert_called()

    # make sure step was updated in database
    step_from_db = repository.get_step_by_id(step.id)
    assert step.name == step_from_db.name
