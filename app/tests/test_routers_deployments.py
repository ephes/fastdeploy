from unittest.mock import patch

import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_deploy_by_user_no_access_token(app, base_url, service):
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-user", json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_deploy_by_user_invalid_access_token(app, base_url, invalid_access_token, service):
    headers = {"authorization": f"Bearer {invalid_access_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-user", headers=headers, json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_by_user_service_not_found(app, base_url, valid_access_token_in_db, service):
    headers = {"authorization": f"Bearer {valid_access_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-user", headers=headers, json=service.dict())

    assert response.status_code == 400
    assert response.json() == {"detail": "Service not found"}


@pytest.mark.asyncio
async def test_deploy_by_user_service_found(app, base_url, valid_access_token_in_db, service_in_db):
    service = service_in_db
    headers = {"authorization": f"Bearer {valid_access_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-user", headers=headers, json=service.dict())

    assert response.status_code == 200
    assert response.json() == {"message": "deploying"}


@pytest.mark.asyncio
async def test_deploy_by_service_no_access_token(app, base_url, service):
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-service", json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_deploy_by_service_invalid_access_token(app, base_url, invalid_service_token, service):
    headers = {"authorization": f"Bearer {invalid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-service", headers=headers, json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_by_service_service_not_found(
    app, base_url, valid_service_token, service, cleanup_database_after_test
):
    headers = {"authorization": f"Bearer {valid_service_token}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-service", headers=headers, json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_deploy_by_service_service_found(app, base_url, valid_service_token_in_db, service_in_db):
    service = service_in_db
    headers = {"authorization": f"Bearer {valid_service_token_in_db}"}
    async with AsyncClient(app=app, base_url=base_url) as client:
        with patch("app.routers.deployments.run_deploy"):
            response = await client.post("/deployments/deploy-by-service", headers=headers, json=service.dict())

    assert response.status_code == 200
    assert response.json() == {"message": "deploying"}
