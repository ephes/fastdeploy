"""
This module contains a collection of authentication related
functions.
"""

from datetime import datetime, timedelta, timezone

from jose import jwt  # type: ignore
from passlib.context import CryptContext  # type: ignore

from . import views
from .config import settings
from .domain.model import Deployment, Service, User
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


async def service_from_token(token: str, uow: AbstractUnitOfWork) -> Service:
    """
    Turn a JWT token into a Service model.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "service":
        raise ValueError("not a service token")

    servicename = payload.get("service")
    if servicename is None:
        raise ValueError("no service name")

    async with uow as uow:
        [service] = await uow.services.get_by_name(servicename)

    service.origin = payload.get("origin", "")
    service.user = payload.get("user", "")
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
        [deployment] = await uow.deployments.get(deployment_id)
    return deployment


async def config_from_token(token: str):
    """
    Turn a JWT token into a config dict.
    """
    payload = token_to_payload(token)
    if payload.get("type") != "config":
        raise ValueError("not a config token")

    return payload
