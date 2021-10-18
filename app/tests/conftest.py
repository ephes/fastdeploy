import pytest

from sqlmodel import Session

from ..auth import get_password_hash
from ..config import settings
from ..main import app as fastapi_app
from ..models import User


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def user_in_db(password):
    user = User(name="user", password=get_password_hash(password), is_active=True)
    with Session(settings.db_engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"
