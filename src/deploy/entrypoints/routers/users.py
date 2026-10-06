from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field

from ... import auth
from ...config import settings
from ...domain import commands, model
from ...domain.model import User
from ..dependencies import get_current_active_user
from ..helper_models import Bus

router = APIRouter()


class UserOut(BaseModel):
    """Just to avoid making private fields like password public."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Return the currently logged in user."""
    return current_user


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), bus: Bus = Depends()) -> dict:
    """Obtain an access token for the current user."""
    try:
        user = await auth.authenticate_user(form_data.username, form_data.password, bus.uow)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        payload={"user": user.name, "type": "user"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


class ServiceIn(BaseModel):
    service: str
    origin: str
    expiration_in_days: int = Field(1, ge=1, le=settings.service_token_max_expire_days)


class ServiceTokenOut(BaseModel):
    service_token: str
    token_type: str
    jti: str
    expires_at: datetime


@router.post("/service-token")
async def service_token(
    service_in: ServiceIn,
    user: Annotated[User, Depends(get_current_active_user)],
    bus: Annotated[Bus, Depends()],
) -> ServiceTokenOut:
    """
    Obtain a service token for the specified service/origin/current_user.

    The token is recorded with its id (`jti`), which can be used to revoke it
    via `DELETE /service-token/{jti}`.
    """
    if user.name is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    token, record = await auth.issue_service_token(
        service=service_in.service,
        origin=service_in.origin,
        user=user.name,
        expires_delta=timedelta(days=service_in.expiration_in_days),
        uow=bus.uow,
    )
    return ServiceTokenOut(service_token=token, token_type="bearer", jti=record.jti, expires_at=record.expires_at)


class RevokedServiceTokenOut(BaseModel):
    detail: str
    jti: str
    revoked_at: datetime


@router.delete(
    "/service-token/{jti}",
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Service token not found"}},
)
async def revoke_service_token(jti: str, bus: Annotated[Bus, Depends()]) -> RevokedServiceTokenOut:
    """
    Revoke a service token by its id (`jti`). Deployments can no longer be
    started with it. Revoking an already revoked token succeeds again.
    """
    try:
        record: model.ServiceToken = await bus.handle(commands.RevokeServiceToken(jti=jti))
    except model.ServiceTokenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service token not found") from e
    assert record.revoked_at is not None
    return RevokedServiceTokenOut(detail=f"Service token {jti} revoked", jti=jti, revoked_at=record.revoked_at)
