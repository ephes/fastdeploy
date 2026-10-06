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


class FinishDeployment(Command):
    deployment_id: int


class StartDeployment(Command):
    service_id: int
    user: str
    origin: str
    context: dict


class ProcessStep(Command):
    name: str
    deployment_id: int
    state: str
    started: datetime
    finished: datetime
    message: str
