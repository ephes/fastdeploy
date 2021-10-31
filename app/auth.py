from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Session, select

from . import database
from .config import settings
from .models import Deployment, Service, User


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


class TokenBase(BaseModel):
    type: str
    exp: int
    item_from_db: Optional[BaseModel]

    def item_exists_in_database(self):
        return self._fetch_item_from_db() is not None

    def _fetch_item_from_db(self):
        print("session: ", Session)
        with Session(database.engine) as session:
            # protect against validating an token from a deleted user / service / deployment
            item = session.exec(self.select_item_stmt).first()
            print("item: ", item, session)
        self.item_from_db = item
        return item

    def validate(self):
        return self.item_exists_in_database()

    @property
    def expires_at(self):
        return datetime.utcfromtimestamp(self.exp)


class UserToken(TokenBase):
    user: str

    @property
    def select_item_stmt(self):
        return select(User).where(User.name == self.user)


class ServiceToken(TokenBase):
    service: str
    origin: str
    user: str

    @property
    def select_item_stmt(self):
        return select(Service).where(Service.name == self.service)


class DeploymentToken(TokenBase):
    deployment: int

    @property
    def select_item_stmt(self):
        return select(Deployment).where(Deployment.id == self.deployment)


def payload_to_token(payload):
    type_to_token = {
        "user": UserToken,
        "service": ServiceToken,
        "deployment": DeploymentToken,
    }
    token_type = type_to_token.get(payload.get("type"))
    if token_type is None:
        raise ValueError("unknown token type")
    return token_type.parse_obj(payload)


def verify_access_token(access_token: str) -> UserToken | ServiceToken | DeploymentToken:
    payload = jwt.decode(
        access_token,
        settings.secret_key,
        algorithms=[settings.password_hash_algorithm],
    )
    token = payload_to_token(payload)
    assert token.validate()
    return token


async def get_current_user(token: str = Depends(OAUTH2_SCHEME)) -> User:
    try:
        token = verify_access_token(token)
        return token.item_from_db
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_service_token(token: str = Depends(OAUTH2_SCHEME)) -> ServiceToken:
    try:
        service_token = verify_access_token(token)
        return service_token
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_deployment(token: str = Depends(OAUTH2_SCHEME)) -> Deployment:
    try:
        deployment_token = verify_access_token(token)
        return deployment_token.item_from_db
    except Exception:
        raise CREDENTIALS_EXCEPTION
