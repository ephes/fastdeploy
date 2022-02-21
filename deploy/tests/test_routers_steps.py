from datetime import datetime

import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_step_no_access_token(app, base_url, step):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(app.url_path_for("process_step_result"), json=step.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_add_step_invalid_access_token(app, base_url, step, invalid_deploy_token):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.dict(),
            headers={"authorization": f"Bearer {invalid_deploy_token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_add_step_deployment_not_found(app, base_url, step, valid_deploy_token):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.dict(),
            headers={"authorization": f"Bearer {valid_deploy_token}"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_add_step(app, base_url, repository, handler, step, valid_deploy_token_in_db, deployment_in_db):
    deployment_in_db.started = datetime.utcnow()
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("process_step_result"),
            json=step.dict(),
            headers={"authorization": f"Bearer {valid_deploy_token_in_db}"},
        )

    assert response.status_code == 200
    actual_step = response.json()
    assert actual_step["id"] > 0
    assert actual_step["name"] == step.name

    # make sure added step was dispatched to event handlers
    handler.last_event.name == step.name

    # make sure step was added to deployment in database
    steps_from_db = await repository.get_steps_by_name(step.name)
    step_from_db = steps_from_db[0]
    assert step_from_db.id > 0
    assert step.name == step_from_db.name


@pytest.mark.asyncio
async def test_get_steps_by_deployment_no_access_token(app, base_url, step_in_db):
    step = step_in_db
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_steps_by_deployment"), params={"deployment_id": step.deployment_id}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_steps_by_deployment(app, base_url, step_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_steps_by_deployment"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            params={"deployment_id": step_in_db.deployment_id},
        )

    assert response.status_code == 200
    steps_by_deployment = response.json()
    assert steps_by_deployment[0]["id"] == step_in_db.id
