import typing

from pathlib import Path

from pydantic import BaseSettings, Field


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
    project_root: Path = ROOT_DIR

    class Config:
        env_file = ROOT_DIR / ".env"


settings = Settings()
