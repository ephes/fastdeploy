from unittest.mock import patch

import pytest

from httpx import AsyncClient
from sqlmodel import Session, select

from .. import database
from ..models import Deployment


@pytest.mark.asyncio
async def test_deploy_no_access_token(app, base_url):
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("deployments")
            response = await client.post(test_url)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_deploy_invalid_access_token(app, base_url, invalid_service_token):
    headers = {"authorization": f"Bearer {invalid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("deployments")
            response = await client.post(test_url, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_service_not_found(app, base_url, valid_service_token, cleanup_database_after_test):
    headers = {"authorization": f"Bearer {valid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        test_url = app.url_path_for("deployments")
        response = await client.post(test_url, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_service(app, base_url, valid_service_token_in_db, service_in_db):
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            test_url = app.url_path_for("deployments")
            response = await client.post(test_url, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"message": "deploying"}

    # make sure deployment was added to service in database
    with Session(database.engine) as session:
        deployment_from_db = session.exec(select(Deployment).where(Deployment.service_id == service_in_db.id)).first()
    assert deployment_from_db.id > 0
