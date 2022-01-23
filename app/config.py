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
    path_for_deploy: str = Field(..., env="PATH_FOR_DEPLOY")
    origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "https://deploy.staging.wersdoerfer.de",
    ]
    project_root: Path = ROOT_DIR
    services_dir_name = Field("services", env="SERVICES_ROOT")
    default_expire_minutes: int = 15
    api_url: str = Field("http://localhost:8000", env="API_URL")
    services_sync_path: str = Field("/services/sync/", env="SERVICES_SYNC_PATH")
    repository: str = Field("sqlite", env="REPOSITORY")
    sudo_user: str = Field("jochen", env="SUDO_USER")

    class Config:
        env_file = ROOT_DIR / ".env"

    @property
    def fastapi_app(self):
        """Avoid circular import."""
        from .main import app as fastapi_app

        return fastapi_app

    @property
    def steps_url(self) -> str:
        steps_path = self.fastapi_app.url_path_for("process_step_result")
        return f"{self.api_url}{steps_path}"

    @property
    def deployment_finish_url(self) -> str:
        deployment_finish_path = self.fastapi_app.url_path_for("finish_deployment")
        return f"{self.api_url}{deployment_finish_path}"

    @property
    def sync_services_url(self) -> str:
        sync_services_path = self.fastapi_app.url_path_for("sync_services")
        return f"{self.api_url}{sync_services_path}"

    @property
    def services_root(self) -> Path:
        return self.project_root / self.services_dir_name


settings = Settings()  # type: ignore
