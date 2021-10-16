import contextlib
import os
import typing

from pathlib import Path

from pydantic import BaseSettings, Field
from sqlmodel import SQLModel, create_engine


ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent


class Settings(BaseSettings):
    app_name: str = "Small Deployment Frontend"
    admin_email: str = "jochen-fastdeploy@wersdoerfer.de"
    password_hash_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str = Field(..., env="DATABASE_URL")
    db_engine: typing.Any
    secret_key: str = Field(..., env="SECRET_KEY")
    test: bool = Field(default=False, env="TEST")
    origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
    ]

    class Config:
        env_file = ROOT_DIR / ".env"


class TestSettings(Settings):
    database_url: str = Field(..., env="TEST_DATABASE_URL")


settings = Settings()
if settings.test:
    settings = TestSettings()


@contextlib.contextmanager
def working_directory(path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


with working_directory(ROOT_DIR):
    # would not work in jupyter notebooks if we didn't
    # change working directory
    settings.db_engine = create_engine(settings.database_url, echo=False)
    SQLModel.metadata.create_all(settings.db_engine)
