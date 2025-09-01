"""
This module is just here to collect all the functions
that are used as dependencies for fastAPI routers.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ..auth import (
    config_from_token,
    deployment_from_token,
    service_from_token,
    user_from_token,
)
from ..domain.model import Deployment, Service, User
from .helper_models import Bus

OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_active_user(
    token: str = Depends(OAUTH2_SCHEME),
    bus: Bus = Depends(),
) -> User:
    try:
        return await user_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_active_service(
    token: str = Depends(OAUTH2_SCHEME),
    bus: Bus = Depends(),
) -> Service:
    try:
        return await service_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_active_deployment(
    token: str = Depends(OAUTH2_SCHEME),
    bus: Bus = Depends(),
) -> Deployment:
    try:
        return await deployment_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_config(token: str = Depends(OAUTH2_SCHEME)):
    try:
        return await config_from_token(token)
    except Exception:
        raise CREDENTIALS_EXCEPTION
