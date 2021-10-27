from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from . import database
from .auth import (
    get_current_deployment,
    get_current_service_and_origin,
    get_current_user,
)
from .models import Deployment, Service, ServiceAndOrigin, User


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


async def get_current_service_and_origin(
    service_and_origin: ServiceAndOrigin = Depends(get_current_service_and_origin),
):
    return service_and_origin


async def get_current_active_deployment(deployment: Deployment = Depends(get_current_deployment)):
    return deployment


def get_service_by_name(name: str) -> Service:
    with Session(database.engine) as session:
        service_from_db = session.exec(select(Service).where(Service.name == name)).first()
    if service_from_db is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service not found",
        )
    return service_from_db
