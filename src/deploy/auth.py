"""
This module contains a collection of authentication related
functions.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt  # type: ignore
from passlib.context import CryptContext  # type: ignore

from . import views
from .config import settings
from .domain.model import Deployment, Service, ServiceToken, User
from .service_layer.unit_of_work import AbstractUnitOfWork

PWD_CONTEXT = CryptContext(schemes=[settings.password_hash_algorithm], deprecated="auto")


def get_password_hash(plain):
    return PWD_CONTEXT.hash(plain)


def verify_password(plain, hashed):
    return PWD_CONTEXT.verify(plain, hashed)


async def authenticate_user(username: str, password: str, uow: AbstractUnitOfWork) -> User:
    """
    Authenticate a user against the database. Raise an exception if the
    user is not found or the password is incorrect.
    """
    user = await views.get_user_by_name(username, uow)

    if not verify_password(password, user.password):
        raise ValueError("invalid password")
    return user


def create_access_token(payload: dict, expires_delta: timedelta | None = None):
    """
    Create an access token from a payload.

    Use a timedelta to set the expiration of the token and use
    the secret_key from settings to sign the token with the sign
    algorithm from settings.
    """
    to_encode = payload.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.token_sign_algorithm)
    return encoded_jwt


def token_to_payload(token: str):
    """
    Parse a JWT token and return a dict of its payload.

    The jwt.decode function checks for expiration and raises
    ExpiredSignatureError if it's expired.
    """
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.token_sign_algorithm],
    )


async def user_from_token(token: str, uow: AbstractUnitOfWork) -> User:
    """
    Turn a JWT token into a User model.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "user":
        raise ValueError("not an access token")

    username = payload.get("user")
    if username is None:
        raise ValueError("no user name")

    return await views.get_user_by_name(username, uow)


async def issue_service_token(
    *, service: str, origin: str, user: str, expires_delta: timedelta, uow: AbstractUnitOfWork
) -> tuple[str, ServiceToken]:
    """
    Record a new service token and return the signed JWT for it. The JWT
    carries the record's ``jti``, so the token can be revoked later.
    """
    issued_at = datetime.now(timezone.utc)
    record = ServiceToken(
        jti=uuid.uuid4().hex,
        service=service,
        origin=origin,
        user=user,
        issued_at=issued_at,
        expires_at=issued_at + expires_delta,
    )
    async with uow:
        await uow.service_tokens.add(record)
        await uow.commit()
    payload = {
        "type": "service",
        "service": service,
        "origin": origin,
        "user": user,
        "jti": record.jti,
    }
    token = jwt.encode(
        {**payload, "exp": record.expires_at}, settings.secret_key, algorithm=settings.token_sign_algorithm
    )
    return token, record


def legacy_service_tokens_accepted(now: datetime) -> bool:
    """Service tokens without a jti are only accepted until the configured point in time."""
    until = settings.legacy_service_tokens_accepted_until
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return now < until


async def service_from_token(token: str, uow: AbstractUnitOfWork) -> Service:
    """
    Turn a JWT token into a Service model.

    The token has to be a recorded, unrevoked service token (or a legacy
    token without ``jti`` while those are still accepted) and the user who
    obtained it has to exist.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "service":
        raise ValueError("not a service token")

    servicename = payload.get("service")
    if servicename is None:
        raise ValueError("no service name")

    username = payload.get("user")
    if not username:
        raise ValueError("no user name")

    jti = payload.get("jti")
    if jti is None and not legacy_service_tokens_accepted(datetime.now(timezone.utc)):
        raise ValueError("legacy service token without jti is no longer accepted")

    async with uow as uow:
        if jti is not None:
            record = await uow.service_tokens.get_by_jti(jti)
            if record is None:
                raise ValueError("unknown service token")
            if record.revoked:
                raise ValueError("service token has been revoked")
            if record.service != servicename or record.user != username:
                raise ValueError("service token does not match its record")
        # raises if the user who obtained the token has been deleted
        await uow.users.get(username)
        service = await uow.services.get_by_name(servicename)

    service.origin = payload.get("origin", "")
    service.user = username
    return service


async def deployment_from_token(token: str, uow: AbstractUnitOfWork) -> Deployment:
    """
    Turn a JWT token into a Deployment model.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "deployment":
        raise ValueError("not a deployment token")

    deployment_id = payload.get("deployment")
    if deployment_id is None:
        raise ValueError("no deployment id")

    async with uow as uow:
        deployment = await uow.deployments.get(deployment_id)
    return deployment


async def config_from_token(token: str):
    """
    Turn a JWT token into a config dict.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "config":
        raise ValueError("not a config token")

    return payload
