from fastapi import Depends

from .auth import get_current_service, get_current_user
from .models import Service, User


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


async def get_current_service(current_service: Service = Depends(get_current_service)):
    print("get current service")
    return current_service
