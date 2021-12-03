import typing

from pathlib import Path

from pydantic import BaseSettings, Field


ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent


class Settings(BaseSettings):
    app_name: str = "Small Deployment Frontend"
    admin_email: str = "jochen-fastdeploy@wersdoerfer.de"
    password_hash_algorithm: str = Field("bcrypt", env="PASSWORD_HASH_ALGORITHM")
    token_sign_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str = Field(..., env="DATABASE_URL")
    db_engine: typing.Any
    secret_key: str = Field(..., env="SECRET_KEY")
    origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "https://deploy.staging.wersdoerfer.de",
    ]
    project_root: Path = ROOT_DIR
    services_root: Path = project_root / Field("services", env="SERVICES_ROOT")
    default_expire_minutes: int = 15
    steps_url: str = Field("http://localhost:8000/steps/", env="STEPS_URL")
    repository: str = Field("sqlite", env="REPOSITORY")
    sudo_user: str = Field("jochen", env="SUDO_USER")

    class Config:
        env_file = ROOT_DIR / ".env"


settings = Settings()
