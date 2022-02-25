from datetime import datetime, timedelta
from typing import Optional, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt  # type: ignore
from passlib.context import CryptContext  # type: ignore
from pydantic import BaseModel

from .bootstrap import get_bus
from .config import settings
from .domain.model import Deployment, Service, User
from .service_layer.messagebus import MessageBus


PWD_CONTEXT = CryptContext(schemes=[settings.password_hash_algorithm], deprecated="auto")
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
    # user = await database.repository.get_user_by_name(username)
    user = None

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
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.token_sign_algorithm)
    return encoded_jwt


class TokenBase(BaseModel):
    type: str
    exp: int
    item_from_db: Optional[BaseModel | User]
    bus: MessageBus

    class Config:
        arbitrary_types_allowed = True

    def item_exists_in_database(self, item_from_db: Optional[BaseModel | User]):
        return self.item_from_db is not None

    async def fetch_item_from_db(self):
        raise NotImplementedError()

    async def on_validation_success(self):
        ...

    async def validate(self):
        self.item_from_db = await self.fetch_item_from_db()
        is_valid = self.item_exists_in_database(self.item_from_db)
        if is_valid:
            await self.on_validation_success()
        return is_valid

    @property
    def expires_at(self):
        return datetime.utcfromtimestamp(self.exp)


class UserToken(TokenBase):
    user: str
    user_model: Optional[User]

    class Config:
        arbitrary_types_allowed = True

    async def on_validation_success(self):
        self.user_model = cast(User, self.item_from_db)

    async def fetch_item_from_db(self) -> Optional[User]:
        [user] = self.bus.uow.users.get(self.user)
        return user


class ServiceToken(TokenBase):
    service: str
    origin: str
    user: str
    service_model: Optional[Service]

    async def on_validation_success(self):
        self.service_model = cast(Service, self.item_from_db)

    async def fetch_item_from_db(self):
        ...
        # return await database.repository.get_service_by_name(self.service)


class DeploymentToken(TokenBase):
    deployment: int

    async def fetch_item_from_db(self):
        ...
        # return await database.repository.get_deployment_by_id(self.deployment)


def payload_to_token(payload, bus: MessageBus) -> UserToken | ServiceToken | DeploymentToken:
    type_to_token = {
        "user": UserToken,
        "service": ServiceToken,
        "deployment": DeploymentToken,
    }
    if (token_type := type_to_token.get(payload.get("type"))) is None:
        raise ValueError("unknown token type")
    # butt ugly FIXME
    if token_type is UserToken:
        return UserToken(**payload, bus=bus)
    elif token_type is ServiceToken:
        return ServiceToken(**payload)
    elif token_type is DeploymentToken:
        return DeploymentToken(**payload)
    else:
        raise ValueError("unknown token type")


async def token_to_payload(token: str):
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.token_sign_algorithm],
    )


async def verify_access_token(access_token: str, bus: MessageBus) -> UserToken | ServiceToken | DeploymentToken:
    payload = await token_to_payload(access_token)
    token = payload_to_token(payload, bus)
    assert await token.validate()
    return token


async def get_user_token_from_access_token(token: str, bus: MessageBus) -> UserToken:
    user_token = await verify_access_token(token, bus)
    assert isinstance(user_token, UserToken)
    assert isinstance(user_token.user_model, User)
    return user_token


async def get_current_user(token: str = Depends(OAUTH2_SCHEME), bus: MessageBus = Depends(get_bus)) -> User:
    try:
        user_token = await get_user_token_from_access_token(token, bus)
        assert isinstance(user_token.user_model, User)
        return user_token.user_model
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_service_token(token: str = Depends(OAUTH2_SCHEME)) -> ServiceToken | UserToken | DeploymentToken:
    try:
        service_token = await verify_access_token(token)
        return service_token
    except Exception:
        raise CREDENTIALS_EXCEPTION


async def get_current_deployment(token: str = Depends(OAUTH2_SCHEME)) -> Deployment:
    try:
        deployment_token = await verify_access_token(token)
        assert isinstance(deployment_token.item_from_db, Deployment)
        return cast(Deployment, deployment_token.item_from_db)
    except Exception:
        raise CREDENTIALS_EXCEPTION