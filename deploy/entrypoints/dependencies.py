"""
This module is just here to collect all the functions
that are used as dependencies for fastAPI routers.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ..auth import deployment_from_token, service_from_token, user_from_token
from ..bootstrap import get_bus
from ..domain.model import Deployment, Service, User
from ..service_layer.messagebus import MessageBus


OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_active_user(
    token: str = Depends(OAUTH2_SCHEME),
    bus: MessageBus = Depends(get_bus),
) -> User:
    try:
        return user_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_active_service(
    token: str = Depends(OAUTH2_SCHEME),
    bus: MessageBus = Depends(get_bus),
) -> Service:
    try:
        return service_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_active_deployment(
    token: str = Depends(OAUTH2_SCHEME),
    bus: MessageBus = Depends(get_bus),
) -> Deployment:
    try:
        return deployment_from_token(token, bus.uow)
    except Exception:
        raise CREDENTIALS_EXCEPTION
