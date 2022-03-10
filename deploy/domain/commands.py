from datetime import datetime

from pydantic import BaseModel


class Command(BaseModel):
    pass


class CreateService(Command):
    name: str
    data: dict


class DeleteService(Command):
    service_id: int


class SyncServices(Command):
    pass


class FinishDeployment(Command):
    id: int


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
    state: str
