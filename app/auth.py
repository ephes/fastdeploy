from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Session, select

from . import database
from .config import settings
from .models import User


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_password_hash(plain):
    return pwd_context.hash(plain)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    servicename: Optional[str] = None


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


def verify_access_token(access_token: str) -> TokenData:
    payload = jwt.decode(
        access_token,
        settings.secret_key,
        algorithms=[settings.password_hash_algorithm],
    )
    username: str = payload.get("user")
    if username is None:
        raise JWTError("no username")
    token_data = TokenData(username=username)
    return token_data


def verify_service_token(service_token: str) -> TokenData:
    payload = jwt.decode(
        service_token,
        settings.secret_key,
        algorithms=[settings.password_hash_algorithm],
    )
    servicename: str = payload.get("service")
    if servicename is None:
        raise JWTError("no service name")
    token_data = TokenData(servicename=servicename)
    return token_data


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = verify_access_token(token)
    except JWTError:
        raise credentials_exception
    with Session(database.engine) as session:
        user = session.exec(select(User).where(User.name == token_data.username)).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_service(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = verify_service_token(token)
    except JWTError:
        raise credentials_exception
    with Session(database.engine) as session:
        user = session.exec(select(User).where(User.name == token_data.username)).first()
    if user is None:
        raise credentials_exception
    return user
