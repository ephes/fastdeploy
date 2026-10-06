import typing
from datetime import datetime
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT_DIR / ".env"), extra="ignore")

    app_name: str = "Small Deployment Frontend"
    admin_email: str = "jochen-fastdeploy@wersdoerfer.de"
    password_hash_algorithm: str = Field("bcrypt")
    token_sign_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    deployment_access_token_expire_minutes: int = 480
    deployment_orphan_reconcile_delay_seconds: int = 300
    # Upper limit for the lifetime of a service token in days.
    service_token_max_expire_days: int = 90
    # Service tokens issued before revocation support have no "jti" claim and
    # cannot be revoked. They are rejected unless this is set to a point in time
    # (ISO 8601 with timezone) until which they are still accepted.
    legacy_service_tokens_accepted_until: datetime | None = None
    # Expired service token records and revoked ones are deleted once their
    # expiry / revocation is older than this many days (on token issue and
    # via "commands.py purgeservicetokens").
    service_token_retention_days: int = Field(30, ge=1)
    database_url: str = "postgresql+asyncpg:///deploy"
    db_engine: typing.Any = None
    secret_key: str = Field(...)
    path_for_deploy: str
    origins: list[str] = [
        "http://localhost",
        "http://localhost:5173",
        "https://deploy.staging.wersdoerfer.de",
    ]
    project_root: Path = ROOT_DIR
    services_dir_name: str = Field("services", alias="services_root")
    default_expire_minutes: int = 15
    api_url: str = Field("http://localhost:8000", alias="api_url")
    services_sync_path: str = Field("/services/sync/", alias="services_sync_path")
    repository: str = Field("sqlite", alias="repository")
    sudo_user: str = Field("jochen", alias="sudo_user")

    @property
    def fastapi_app(self):
        """Avoid circular import."""
        from .entrypoints.fastapi_app import app as fastapi_app

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
