from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from . import database
from .config import settings
from .models import Deployment, Service, ServiceAndOrigin, User


PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_password_hash(plain):
    return PWD_CONTEXT.hash(plain)


def verify_password(plain, hashed):
    return PWD_CONTEXT.verify(plain, hashed)


async def authenticate_user(username: str, password: str):
    with Session(database.engine) as session:
        statement = select(User).where(User.name == username)
        results = session.exec(statement)
        user = results.first()

    if not user:
        return False
    if not verify_password(password, user.password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.password_hash_algorithm)
    return encoded_jwt


def verify_access_token(access_token: str) -> dict:
    return jwt.decode(
        access_token,
        settings.secret_key,
        algorithms=[settings.password_hash_algorithm],
    )


def verify_user_token(access_token: str) -> str:
    payload = verify_access_token(access_token)
    if (username := payload.get("user")) is None:
        raise JWTError("no username")
    return username


def verify_service_token(access_token: str) -> (str, str):
    payload = verify_access_token(access_token)
    if (service_name := payload.get("service")) is None:
        raise JWTError("no service name")
    if (origin := payload.get("origin")) is None:
        raise JWTError("no service origin")
    return service_name, origin


def verify_deployment_token(access_token: str) -> int:
    payload = verify_access_token(access_token)
    if (deployment_id := payload.get("deployment")) is None:
        raise JWTError("no deployment id")
    return deployment_id


async def get_current_user(token: str = Depends(OAUTH2_SCHEME)) -> User:
    try:
        username = verify_user_token(token)
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    with Session(database.engine) as session:
        # protect against validating an access_token from a deleted user
        user = session.exec(select(User).where(User.name == username)).first()
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user


async def get_current_service_and_origin(token: str = Depends(OAUTH2_SCHEME)) -> ServiceAndOrigin:
    try:
        service_name, origin = verify_service_token(token)
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    with Session(database.engine) as session:
        # protect against validating an access_token from a deleted service
        service = session.exec(select(Service).where(Service.name == service_name)).first()
    if service is None:
        raise CREDENTIALS_EXCEPTION
    return ServiceAndOrigin(service=service, origin=origin)


async def get_current_deployment(token: str = Depends(OAUTH2_SCHEME)) -> Deployment:
    try:
        deployment_id = verify_deployment_token(token)
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    with Session(database.engine) as session:
        # protect against validating an access_token from a deleted deployment
        deployment = session.exec(select(Deployment).where(Deployment.id == deployment_id)).first()
    if deployment is None:
        raise CREDENTIALS_EXCEPTION
    return deployment
