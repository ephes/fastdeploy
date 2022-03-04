from datetime import datetime, timedelta

import pytest

# from fastapi import HTTPException
# from httpx import AsyncClient
from sqlalchemy.orm.exc import NoResultFound

from deploy.auth import (
    authenticate_user,
    create_access_token,
    token_to_payload,
    user_from_token,
    verify_password,
)
from deploy.config import settings


# from unittest.mock import AsyncMock, patch


# from deploy.routers.users import UserOut

pytestmark = pytest.mark.asyncio


# async def test_database_fixture(async_database):
#     print("database: ", async_database)
#     assert False


async def test_verify_password(user, password):
    assert verify_password(password, user.password)
    assert not verify_password("", user.password)


async def test_authenticate_user_not_in_db(uow):
    with pytest.raises((NoResultFound, StopIteration)):
        await authenticate_user("foobar", "bar", uow)


async def test_authenticate_user_wrong_password(user_in_db, uow):
    user = user_in_db
    assert not await authenticate_user(user.name, f"{user.password}foo", uow)


async def test_authenticate_happy(user_in_db, password, uow):
    user = user_in_db
    user_from_db = await authenticate_user(user.name, password, uow)
    assert user_in_db == user_from_db


async def test_create_access_token_without_expire():
    access_token = create_access_token(payload={"type": "user", "user": "user"})
    payload = token_to_payload(access_token)
    expires_at = datetime.utcfromtimestamp(payload["exp"])
    expected_expire = datetime.utcnow() + timedelta(minutes=settings.default_expire_minutes)
    diff_seconds = (expected_expire - expires_at).total_seconds()
    assert diff_seconds < 1


async def test_user_from_token_value_error(uow):
    token = create_access_token(payload={"type": "asdf", "user": "user", "exp": 123})
    with pytest.raises(ValueError):
        await user_from_token(token, uow)


async def test_user_from_token_happy(user_in_db, uow):
    token = create_access_token(payload={"type": "user", "user": "user", "exp": 123})
    verified_user = await user_from_token(token, uow)
    assert verified_user == user_in_db


# @pytest.mark.parametrize(
#     "payload",
#     [
#         {"type": "user", "user": "user", "exp": 123},
#         {"type": "service", "service": "fastdeploy", "origin": "GitHub", "user": "user", "exp": 123},
#         {"type": "deployment", "deployment": 1, "exp": 123},
#     ],
# )
# @pytest.mark.asyncio
# async def test_payload_to_token_valid(payload):
#     token = payload_to_token(payload)
#     repository = AsyncMock()
#     with patch("app.database.repository", new=repository):
#         assert await token.validate()


# @pytest.mark.parametrize(
#     "payload",
#     [
#         {"type": "asdf", "user": "user", "exp": 123},
#         {"user": "user", "exp": 123},
#     ],
# )
# def test_payload_to_token_type_value_error(payload):
#     with pytest.raises(ValueError):
#         payload_to_token(payload)


# @pytest.mark.asyncio
# async def test_get_current_user_not_in_db(valid_access_token):
#     with pytest.raises(HTTPException):
#         await get_current_user(valid_access_token)


# @pytest.mark.asyncio
# async def test_login_required_without_token(app, base_url, user, password):
#     async with AsyncClient(app=app, base_url=base_url) as client:
#         response = await client.get("/users/me")

#     assert response.status_code == 401
#     assert response.json() == {"detail": "Not authenticated"}


# @pytest.mark.asyncio
# async def test_api_token(app, base_url, user_in_db, password):
#     user = user_in_db
#     # post username + password to login to get access token
#     async with AsyncClient(app=app, base_url=base_url) as ac:
#         response = await ac.post("/token", data={"username": user.name, "password": password})
#     assert response.status_code == 200
#     access_token = response.json().get("access_token")
#     assert access_token is not None

#     # use fetched token to assert we are authenticated now
#     headers = {"authorization": f"Bearer {access_token}"}
#     async with AsyncClient(app=app, base_url=base_url) as ac:
#         response = await ac.get("/users/me", headers=headers)

#     assert response.status_code == 200
#     assert response.json() == UserOut.from_orm(user).dict()
