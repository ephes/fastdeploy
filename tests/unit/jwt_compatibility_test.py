"""Fixtures minted with python-jose 3.5.0, HS256 and test-secret-key before removal."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from deploy import auth
from deploy.config import Settings, settings
from deploy.entrypoints import dependencies

FIXTURES = json.loads((Path(__file__).parents[1] / "fixtures/python_jose_tokens.json").read_text())


@pytest.mark.parametrize("name", ["user", "service", "legacy", "deployment", "config", "no_exp"])
def test_old_library_tokens_verify(name):
    assert auth.token_to_payload(FIXTURES[name]["signed"]) == FIXTURES[name]["claims"]


@pytest.mark.parametrize("name", ["expired", "wrong_algorithm", "tampered", "none"])
def test_invalid_tokens_rejected(name):
    with pytest.raises(jwt.InvalidTokenError):
        auth.token_to_payload(invalid_token(name))


def invalid_token(name):
    if name == "tampered":
        signed = FIXTURES["user"]["signed"]
        header, payload, signature = signed.split(".")
        return ".".join([header, payload, ("A" if signature[0] != "A" else "B") + signature[1:]])
    if name == "none":
        return jwt.encode(FIXTURES["user"]["claims"], key="", algorithm="none")
    return FIXTURES[name]["signed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["expired", "wrong_algorithm", "tampered", "none"])
@pytest.mark.parametrize(
    "getter",
    [
        dependencies.get_current_active_user,
        dependencies.get_current_active_service,
        dependencies.get_current_active_deployment,
        dependencies.get_current_config,
    ],
)
async def test_http_error_mapping(name, getter, in_memory_uow):
    kwargs = {} if getter is dependencies.get_current_config else {"bus": SimpleNamespace(uow=in_memory_uow)}
    with pytest.raises(HTTPException) as exc:
        await getter(token=invalid_token(name), **kwargs)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_expiry_whole_second_boundary(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime.fromtimestamp(2000000000.75, timezone.utc)

    monkeypatch.setattr(auth, "datetime", Clock)
    assert auth.token_to_payload(jwt.encode({"exp": 2000000000}, settings.secret_key, algorithm="HS256"))
    with pytest.raises(jwt.ExpiredSignatureError):
        auth.token_to_payload(jwt.encode({"exp": 1999999999}, settings.secret_key, algorithm="HS256"))
    with pytest.raises(jwt.ImmatureSignatureError):
        auth.token_to_payload(jwt.encode({"nbf": 4102444800}, settings.secret_key, algorithm="HS256"))
    assert auth.token_to_payload(jwt.encode({"iat": 4102444800}, settings.secret_key, algorithm="HS256"))


@pytest.mark.parametrize("algorithm", ["none", "RS256", "bogus"])
def test_algorithm_configuration_rejects_unsupported_values(algorithm):
    with pytest.raises(ValidationError):
        Settings(secret_key="test-secret-key", path_for_deploy="/tmp/deploy", token_sign_algorithm=algorithm)


@pytest.mark.asyncio
async def test_old_recorded_service_token_revocation(in_memory_uow, service, user):
    from deploy.domain.model import ServiceToken

    async with in_memory_uow:
        await in_memory_uow.services.add(service)
        await in_memory_uow.users.add(user)
        record = ServiceToken(
            jti="old-jti",
            service=service.name,
            user=user.name,
            origin="GitHub",
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.fromtimestamp(4102444800, timezone.utc),
        )
        await in_memory_uow.service_tokens.add(record)
        await in_memory_uow.commit()
    signed = FIXTURES["service"]["signed"]
    assert await auth.service_from_token(signed, in_memory_uow) == service
    record.revoked_at = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="revoked"):
        await auth.service_from_token(signed, in_memory_uow)


@pytest.mark.asyncio
async def test_old_legacy_service_token_grace(in_memory_uow, service, user, monkeypatch):
    async with in_memory_uow:
        await in_memory_uow.services.add(service)
        await in_memory_uow.users.add(user)
        await in_memory_uow.commit()
    monkeypatch.setattr(
        settings, "legacy_service_tokens_accepted_until", datetime.fromtimestamp(4102444800, timezone.utc)
    )
    assert await auth.service_from_token(FIXTURES["legacy"]["signed"], in_memory_uow) == service
    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", datetime.fromtimestamp(1, timezone.utc))
    with pytest.raises(ValueError, match="legacy"):
        await auth.service_from_token(FIXTURES["legacy"]["signed"], in_memory_uow)
