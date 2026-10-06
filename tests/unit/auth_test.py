from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm.exc import NoResultFound

from deploy.auth import (
    authenticate_user,
    create_access_token,
    deployment_from_token,
    issue_service_token,
    service_from_token,
    token_to_payload,
    user_from_token,
    verify_password,
)
from deploy.config import settings
from deploy.domain import commands, model

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
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    expected_expire = datetime.now(timezone.utc) + timedelta(minutes=settings.default_expire_minutes)
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


async def issue(uow, service="fastdeploy", user="user", minutes=5):
    return await issue_service_token(
        service=service, origin="GitHub", user=user, expires_delta=timedelta(minutes=minutes), uow=uow
    )


async def test_service_from_token_not_in_db(user_in_db, uow):
    token, _ = await issue(uow, service="fastdeploy", user=user_in_db.name)
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await service_from_token(token, uow)


async def test_service_from_token_happy(service_in_db, user_in_db, uow):
    token, record = await issue(uow, service=service_in_db.name, user=user_in_db.name)
    assert token_to_payload(token)["jti"] == record.jti
    verified_service = await service_from_token(token, uow)
    assert verified_service == service_in_db
    assert verified_service.origin == "GitHub"
    assert verified_service.user == user_in_db.name


async def test_issue_service_token_records_token(user_in_db, uow):
    token, record = await issue(uow, service="fastdeploy", user=user_in_db.name, minutes=60)
    async with uow:
        stored = await uow.service_tokens.get_by_jti(record.jti)
    assert stored is not None
    assert (stored.service, stored.user, stored.origin, stored.revoked_at) == (
        "fastdeploy",
        user_in_db.name,
        "GitHub",
        None,
    )
    expires_at = datetime.fromtimestamp(token_to_payload(token)["exp"], tz=timezone.utc)
    assert abs((stored.expires_at - expires_at).total_seconds()) < 1


async def test_service_from_token_unknown_jti(service_in_db, user_in_db, uow):
    payload = {"type": "service", "service": service_in_db.name, "user": user_in_db.name, "jti": "unknown"}
    token = create_access_token(payload=payload, expires_delta=timedelta(minutes=5))
    with pytest.raises(ValueError, match="unknown service token"):
        await service_from_token(token, uow)


async def test_service_from_token_revoked(bus, service_in_db, user_in_db, uow):
    token, record = await issue(uow, service=service_in_db.name, user=user_in_db.name)
    await bus.handle(commands.RevokeServiceToken(jti=record.jti))
    with pytest.raises(ValueError, match="revoked"):
        await service_from_token(token, uow)


async def test_revoke_unknown_service_token(bus):
    with pytest.raises(model.ServiceTokenNotFound):
        await bus.handle(commands.RevokeServiceToken(jti="unknown"))


async def test_service_from_token_record_mismatch(service_in_db, user_in_db, uow):
    _, record = await issue(uow, service="other-service", user=user_in_db.name)
    payload = {"type": "service", "service": service_in_db.name, "user": user_in_db.name, "jti": record.jti}
    token = create_access_token(payload=payload, expires_delta=timedelta(minutes=5))
    with pytest.raises(ValueError, match="does not match"):
        await service_from_token(token, uow)


async def test_service_from_token_deleted_user(service_in_db, uow):
    # the record exists, but the user who obtained the token does not (anymore)
    token, _ = await issue(uow, service=service_in_db.name, user="deleted-user")
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await service_from_token(token, uow)


def legacy_token(service_name, user_name="user"):
    payload = {"type": "service", "service": service_name, "origin": "GitHub", "user": user_name}
    return create_access_token(payload=payload, expires_delta=timedelta(minutes=5))


async def test_service_from_token_legacy_rejected_by_default(service_in_db, user_in_db, uow, monkeypatch):
    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", None)
    with pytest.raises(ValueError, match="legacy"):
        await service_from_token(legacy_token(service_in_db.name, user_in_db.name), uow)


async def test_service_from_token_legacy_accepted_until(service_in_db, user_in_db, uow, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", now + timedelta(days=1))
    verified_service = await service_from_token(legacy_token(service_in_db.name, user_in_db.name), uow)
    assert verified_service == service_in_db

    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", now - timedelta(seconds=1))
    with pytest.raises(ValueError, match="legacy"):
        await service_from_token(legacy_token(service_in_db.name, user_in_db.name), uow)


async def test_service_from_token_legacy_naive_datetime_is_utc(service_in_db, user_in_db, uow, monkeypatch):
    until = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", until)
    assert await service_from_token(legacy_token(service_in_db.name, user_in_db.name), uow) == service_in_db


async def test_service_from_token_legacy_deleted_user(service_in_db, uow, monkeypatch):
    monkeypatch.setattr(
        settings, "legacy_service_tokens_accepted_until", datetime.now(timezone.utc) + timedelta(days=1)
    )
    with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
        await service_from_token(legacy_token(service_in_db.name, "deleted-user"), uow)


async def test_service_from_token_without_user_is_rejected(service_in_db, uow, monkeypatch):
    monkeypatch.setattr(
        settings, "legacy_service_tokens_accepted_until", datetime.now(timezone.utc) + timedelta(days=1)
    )
    token = create_access_token({"type": "service", "service": service_in_db.name}, timedelta(minutes=5))
    with pytest.raises(ValueError, match="no user name"):
        await service_from_token(token, uow)


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
