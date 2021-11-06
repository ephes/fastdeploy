from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from fastapi import HTTPException
from httpx import AsyncClient

from ..auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    payload_to_token,
    verify_access_token,
    verify_password,
)
from ..config import settings
from ..routers.users import UserOut


def test_verify_password(user, password):
    assert verify_password(password, user.password)
    assert not verify_password("", user.password)


@pytest.mark.asyncio
async def test_authenticate_user_not_in_db():
    assert not await authenticate_user("foobar", "bar")


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(user_in_db):
    user = user_in_db
    assert not await authenticate_user(user.name, f"{user.password}foo")


def test_create_access_token_without_expire():
    access_token = create_access_token(data={"type": "user", "user": "user"})
    with patch("app.database.repository"):
        token = verify_access_token(access_token)
    expected_expire = datetime.utcnow() + timedelta(minutes=settings.default_expire_minutes)
    diff_seconds = (expected_expire - token.expires_at).total_seconds()
    assert diff_seconds < 1


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "user", "user": "user", "exp": 123},
        {"type": "service", "service": "fastdeploy", "origin": "GitHub", "user": "user", "exp": 123},
        {"type": "deployment", "deployment": 1, "exp": 123},
    ],
)
def test_payload_to_token_valid(payload):
    token = payload_to_token(payload)
    with patch("app.database.repository"):
        assert token.validate()


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "asdf", "user": "user", "exp": 123},
        {"user": "user", "exp": 123},
    ],
)
def test_payload_to_token_type_value_error(payload):
    with pytest.raises(ValueError):
        payload_to_token(payload)


@pytest.mark.asyncio
async def test_get_current_user_not_in_db(valid_access_token):
    with pytest.raises(HTTPException):
        await get_current_user(valid_access_token)


@pytest.mark.asyncio
async def test_login_required_without_token(app, base_url, user, password):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_api_token(app, base_url, user_in_db, password):
    user = user_in_db
    # post username + password to login to get access token
    async with AsyncClient(app=app, base_url=base_url) as ac:
        response = await ac.post("/token", data={"username": user.name, "password": password})
    assert response.status_code == 200
    access_token = response.json().get("access_token")
    assert access_token is not None

    # use fetched token to assert we are authenticated now
    headers = {"authorization": f"Bearer {access_token}"}
    async with AsyncClient(app=app, base_url=base_url) as ac:
        response = await ac.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == UserOut.from_orm(user).dict()
