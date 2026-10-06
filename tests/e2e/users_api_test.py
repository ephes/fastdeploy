from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from deploy.adapters import orm
from deploy.auth import service_from_token
from deploy.config import settings
from deploy.entrypoints.routers.users import ServiceIn, UserOut

pytestmark = pytest.mark.asyncio


async def test_login_required_without_token(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("read_users_me"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_api_token(app, user_in_db, password):
    user = user_in_db
    # post username + password to login to get access token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            app.url_path_for("login_for_access_token"), data={"username": user.name, "password": password}
        )
    assert response.status_code == 200
    access_token = response.json().get("access_token")
    assert access_token is not None

    # use fetched token to assert we are authenticated now
    headers = {"authorization": f"Bearer {access_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == UserOut.model_validate(user).model_dump()


@pytest.fixture
def service_in(service):
    return ServiceIn(service=service.name, origin="GitHub")


async def test_fetch_service_token_no_access_token(app, service_in):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(app.url_path_for("service_token"), json=service_in.model_dump())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_fetch_service_token(app, service_in, service_in_db, valid_access_token_in_db, uow):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("service_token"),
            json=service_in.model_dump(),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    body = response.json()
    token = body["service_token"]
    service_token = await service_from_token(token, uow)
    assert service_in.service == service_token.name
    async with uow:
        record = await uow.service_tokens.get_by_jti(body["jti"])
    assert record.service == service_in.service
    assert record.revoked_at is None


async def fetch_service_token(app, access_token, service_in, expiration_in_days=1):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            app.url_path_for("service_token"),
            json={**service_in.model_dump(), "expiration_in_days": expiration_in_days},
            headers={"authorization": f"Bearer {access_token}"},
        )


async def start_deployment(app, service_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            app.url_path_for("start_deployment"), headers={"authorization": f"Bearer {service_token}"}
        )


async def revoke(app, access_token, jti):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.delete(
            app.url_path_for("revoke_service_token", jti=jti),
            headers={"authorization": f"Bearer {access_token}"},
        )


async def test_fetch_service_token_expiration_limit(app, service_in, valid_access_token_in_db):
    max_days = settings.service_token_max_expire_days
    response = await fetch_service_token(app, valid_access_token_in_db, service_in, expiration_in_days=max_days)
    assert response.status_code == 200
    response = await fetch_service_token(app, valid_access_token_in_db, service_in, expiration_in_days=max_days + 1)
    assert response.status_code == 422


@patch("deploy.tasks.subprocess.Popen")
async def test_revoked_service_token_cannot_deploy(popen, app, service_in, service_in_db, valid_access_token_in_db):
    response = await fetch_service_token(app, valid_access_token_in_db, service_in)
    token, jti = response.json()["service_token"], response.json()["jti"]

    response = await revoke(app, valid_access_token_in_db, jti)
    assert response.status_code == 200
    body = response.json()
    assert body["jti"] == jti
    revoked_at = body["revoked_at"]

    response = await start_deployment(app, token)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    popen.assert_not_called()

    # revoking again succeeds and keeps the first revocation time
    response = await revoke(app, valid_access_token_in_db, jti)
    assert response.status_code == 200
    assert response.json()["revoked_at"] == revoked_at


@patch("deploy.tasks.subprocess.Popen")
async def test_unrevoked_service_token_can_deploy(popen, app, service_in, service_in_db, valid_access_token_in_db):
    response = await fetch_service_token(app, valid_access_token_in_db, service_in)
    response = await start_deployment(app, response.json()["service_token"])
    assert response.status_code == 200
    popen.assert_called_once()


async def test_revoke_unknown_service_token(app, valid_access_token_in_db):
    response = await revoke(app, valid_access_token_in_db, "unknown")
    assert response.status_code == 404
    assert response.json() == {"detail": "Service token not found"}


async def test_revoke_service_token_requires_user_token(app, valid_service_token_in_db):
    response = await revoke(app, valid_service_token_in_db, "unknown")
    assert response.status_code == 401


@patch("deploy.tasks.subprocess.Popen")
async def test_service_token_of_deleted_user_cannot_deploy(
    popen, app, uow, service_in, service_in_db, user_in_db, valid_access_token_in_db
):
    response = await fetch_service_token(app, valid_access_token_in_db, service_in)
    token = response.json()["service_token"]
    async with uow:
        await uow.session.execute(delete(orm.users).where(orm.users.c.name == user_in_db.name))
        await uow.commit()

    response = await start_deployment(app, token)
    assert response.status_code == 401
    popen.assert_not_called()
