from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from pydantic.types import conint

from ... import auth
from ...bootstrap import get_bus
from ...config import settings
from ...domain.model import User
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_user


router = APIRouter()


class UserOut(BaseModel):
    """Just to avoid making private fields like password public."""

    id: int
    name: str

    class Config:
        orm_mode = True


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Return the currently logged in user."""
    return current_user


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), bus: MessageBus = Depends(get_bus)):
    """Obtain an access token for the current user."""
    try:
        user = await auth.authenticate_user(form_data.username, form_data.password, bus.uow)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        payload={"user": user.name, "type": "user"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


class ServiceIn(BaseModel):
    service: str
    origin: str
    expiration_in_days: conint(ge=1, le=180) = 1  # type: ignore


@router.post("/service-token")
async def service_token(service_in: ServiceIn, user: User = Depends(get_current_active_user)):
    """Obtain a service token for the specified service/origin/current_user."""
    payload = {
        "type": "service",
        "service": service_in.service,
        "origin": service_in.origin,
        "user": user.name,
    }
    service_token_expires = timedelta(days=service_in.expiration_in_days)
    token = auth.create_access_token(payload=payload, expires_delta=service_token_expires)
    return {"service_token": token, "token_type": "bearer"}
