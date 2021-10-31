from fastapi import Depends

from .auth import (
    ServiceToken,
    get_current_deployment,
    get_current_service_token,
    get_current_user,
)
from .models import Deployment, User


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


async def get_current_service_token(
    service_token: ServiceToken = Depends(get_current_service_token),
):
    return service_token


async def get_current_deployment(deployment: Deployment = Depends(get_current_deployment)):
    return deployment
