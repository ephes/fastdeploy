from datetime import datetime

from pydantic import BaseModel


class Command(BaseModel):
    pass


class CreateUser(Command):
    username: str
    password_hash: str


class CreateService(Command):
    name: str
    data: dict


class DeleteService(Command):
    service_id: int


class SyncServices(Command):
    # Allow a sync that deletes all or more than half of the services.
    force: bool = False
    confirmation: str | None = None


class RevokeServiceToken(Command):
    jti: str


class PurgeServiceTokens(Command):
    retention_days: int


class FinishDeployment(Command):
    # None is for trusted internal callers; HTTP must carry its issuing JWT.
    deployment_token: str | None = None
    deployment_id: int


class FinishOrphanedDeployment(Command):
    """Finish a deployment its deploy task stopped reporting for, as failed."""

    deployment_id: int


class StartDeployment(Command):
    # None is reserved for trusted internal callers; HTTP always supplies its JWT.
    service_token: str | None = None
    service_id: int
    user: str
    origin: str
    context: dict


class ProcessStep(Command):
    deployment_token: str | None = None
    name: str
    deployment_id: int
    state: str
    started: datetime
    finished: datetime
    message: str
