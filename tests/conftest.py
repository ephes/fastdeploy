import pytest

from deploy.entrypoints.fastapi_app import app as fastapi_app


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"
