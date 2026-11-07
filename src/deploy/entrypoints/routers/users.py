import asyncio
from datetime import datetime, timedelta
from threading import BoundedSemaphore
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import NoResultFound

from ... import auth
from ...config import settings
from ...domain import commands, model
from ...domain.model import User
from ...login_throttle import login_throttle
from ..dependencies import get_current_active_user
from ..helper_models import Bus

router = APIRouter()
login_capacity = BoundedSemaphore(settings.login_max_concurrent)


class UserOut(BaseModel):
    """Just to avoid making private fields like password public."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Return the currently logged in user."""
    return current_user


@router.post("/token", responses={429: {"description": "Too many failed login attempts"}})
async def login_for_access_token(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends(), bus: Bus = Depends()
) -> dict:
    """
    Obtain an access token for the current user.

    Failed attempts are limited per user name and client address and per client
    address (`LOGIN_FAILURE_LIMIT`, `LOGIN_ADDRESS_FAILURE_LIMIT`,
    `LOGIN_FAILURE_WINDOW_SECONDS`). At the limit the request is answered with
    429 and a `Retry-After` header, without checking the password.
    """
    address = request.client.host if request.client else "unknown"
    retry_after = login_throttle.retry_after(form_data.username, address)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    if not login_capacity.acquire(blocking=False):
        raise HTTPException(
            status_code=429, detail="Login capacity reached; try again shortly", headers={"Retry-After": "1"}
        )
    attempt = login_throttle.begin_attempt(form_data.username, address)
    try:
        try:
            user = await auth.authenticate_user(form_data.username, form_data.password, bus.uow)
        except (auth.InvalidCredentials, NoResultFound):
            login_throttle.record_failure(attempt)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except asyncio.CancelledError:
            login_throttle.record_failure(attempt)
            raise
        except Exception:
            login_throttle.discard_attempt(attempt)
            raise
        login_throttle.record_success(attempt)
    finally:
        login_capacity.release()
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


@router.post(
    "/service-token",
    responses={
        403: {"description": "Service token issuance requires an administrator"},
        422: {"description": "Unknown service/user, blank origin or invalid token lifetime"},
    },
)
async def service_token(
    service_in: ServiceIn,
    user: Annotated[User, Depends(get_current_active_user)],
    bus: Annotated[Bus, Depends()],
) -> ServiceTokenOut:
    """
    Obtain a service token for the specified service/origin/current_user.
    Requires membership in SERVICE_TOKEN_ADMIN_USERS (otherwise 403).

    The token is recorded with its id (`jti`), which can be used to revoke it
    via `DELETE /service-token/{jti}`.
    """
    if user.name is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    if user.name not in settings.service_token_admin_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Service token issuance requires an administrator"
        )
    try:
        token, record = await auth.issue_service_token_for_existing(
            service=service_in.service,
            origin=service_in.origin,
            user=user.name,
            days=service_in.expiration_in_days,
            uow=bus.uow,
        )
    except auth.ServiceTokenIssueRefused as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    return ServiceTokenOut(service_token=token, token_type="bearer", jti=record.jti, expires_at=record.expires_at)


class RevokedServiceTokenOut(BaseModel):
    detail: str
    jti: str
    revoked_at: datetime


@router.delete(
    "/service-token/{jti}",
    responses={
        403: {"description": "Service token revocation requires an administrator"},
        404: {"description": "Service token not found"},
    },
)
async def revoke_service_token(
    jti: str, user: Annotated[User, Depends(get_current_active_user)], bus: Annotated[Bus, Depends()]
) -> RevokedServiceTokenOut:
    """
    Revoke a service token by its id (`jti`). Deployments can no longer be
    started with it. Requires membership in SERVICE_TOKEN_ADMIN_USERS.
    Revoking an already revoked token succeeds again.
    """
    if user.name not in settings.service_token_admin_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Service token revocation requires an administrator"
        )
    try:
        record: model.ServiceToken = await bus.handle(commands.RevokeServiceToken(jti=jti))
    except model.ServiceTokenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service token not found") from e
    assert record.revoked_at is not None
    return RevokedServiceTokenOut(detail=f"Service token {jti} revoked", jti=jti, revoked_at=record.revoked_at)
