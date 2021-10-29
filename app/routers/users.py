from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from .. import auth
from ..config import settings
from ..dependencies import get_current_active_user
from ..models import ServiceAndOrigin, User


router = APIRouter()


class UserOut(BaseModel):
    """Just to avoid making private fields like password public."""

    id: int
    name: str

    class Config:
        orm_mode = True


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        data={"user": user.name, "type": "user"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/service-token")
async def service_token(service_and_origin: ServiceAndOrigin, user: User = Depends(get_current_active_user)):
    service_token_expires = timedelta(minutes=30)
    data = {
        "type": "service",
        "service": service_and_origin.service.name,
        "origin": service_and_origin.origin,
        "user": user.name,
    }
    token = auth.create_access_token(data=data, expires_delta=service_token_expires)
    return {"service_token": token, "token_type": "bearer"}
