import pytest

from sqlmodel import Session, select

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
    # user does not get refreshed - bug in sqlmodel? FIXME
    user = User(name="user", password=get_password_hash(password), is_active=True)
    user_copy = user.copy()
    with Session(settings.db_engine) as session:
        session.add(user)
        session.commit()
    with Session(settings.db_engine) as session:
        user = session.exec(select(User).where(User.name == user_copy.name)).first()
    return user


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"
