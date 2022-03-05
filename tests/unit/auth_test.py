from datetime import datetime, timedelta

import pytest

from sqlalchemy.orm.exc import NoResultFound

from deploy.auth import (
    authenticate_user,
    create_access_token,
    deployment_from_token,
    service_from_token,
    token_to_payload,
    user_from_token,
    verify_password,
)
from deploy.config import settings


pytestmark = pytest.mark.asyncio


async def test_verify_password(user, password):
    assert verify_password(password, user.password)
    assert not verify_password("", user.password)


async def test_authenticate_user_not_in_db(uow):
    with pytest.raises((NoResultFound, StopIteration)):
        await authenticate_user("foobar", "bar", uow)


async def test_authenticate_user_wrong_password(user_in_db, uow):
    user = user_in_db
    with pytest.raises(ValueError):
        await authenticate_user(user.name, f"{user.password}foo", uow)


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


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "asdf", "user": "user", "exp": 123},
        {"type": "user", "exp": 123},
    ],
)
async def test_user_from_token_value_error(payload, uow):
    token = create_access_token(payload=payload)
    with pytest.raises(ValueError):
        await user_from_token(token, uow)


async def test_user_from_token_not_in_db(uow):
    payload = {"type": "user", "user": "user", "exp": 123}
    token = create_access_token(payload=payload)
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await user_from_token(token, uow)


async def test_user_from_token_happy(user_in_db, uow):
    token = create_access_token(payload={"type": "user", "user": user_in_db.name, "exp": 123})
    verified_user = await user_from_token(token, uow)
    assert verified_user == user_in_db


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "asdf", "service": "fastdeploy", "exp": 123},
        {"type": "service", "exp": 123},
    ],
)
async def test_service_from_token_value_error(payload, uow):
    token = create_access_token(payload=payload)
    with pytest.raises(ValueError):
        await service_from_token(token, uow)


async def test_service_from_token_not_in_db(uow):
    payload = {"type": "service", "service": "fastdeploy", "exp": 123}
    token = create_access_token(payload=payload)
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await service_from_token(token, uow)


async def test_service_from_token_happy(service_in_db, uow):
    payload = {"type": "service", "service": service_in_db.name, "origin": "GitHub", "exp": 123}
    token = create_access_token(payload=payload)
    verified_service = await service_from_token(token, uow)
    assert verified_service == service_in_db


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "asdf", "deployment": 23, "exp": 123},
        {"type": "deployment", "exp": 123},
    ],
)
async def test_deployment_from_token_value_error(payload, uow):
    token = create_access_token(payload=payload)
    with pytest.raises(ValueError):
        await deployment_from_token(token, uow)


async def test_deployment_from_token_not_in_db(uow):
    payload = {"type": "deployment", "deployment": 23, "exp": 123}
    token = create_access_token(payload=payload)
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await deployment_from_token(token, uow)


async def test_deployment_from_token_happy(deployment_in_db, uow):
    payload = {"type": "deployment", "deployment": deployment_in_db.id, "exp": 123}
    token = create_access_token(payload=payload)
    verified_deployment = await deployment_from_token(token, uow)
    assert verified_deployment == deployment_in_db
