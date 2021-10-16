import pytest

from ..auth import get_password_hash
from ..models import User
from ..views import app as fastapi_app


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"
