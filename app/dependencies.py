from fastapi import Depends

from .auth import (
    get_current_deployment,
    get_current_service_and_origin,
    get_current_user,
)
from .models import Deployment, ServiceAndOrigin, User


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


async def get_current_service_and_origin(
    service_and_origin: ServiceAndOrigin = Depends(get_current_service_and_origin),
):
    return service_and_origin


async def get_current_active_deployment(deployment: Deployment = Depends(get_current_deployment)):
    return deployment
