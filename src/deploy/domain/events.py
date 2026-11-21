from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EVENT_TYPES = Literal["authentication", "service", "step", "deployment", "user"]


class Event(BaseModel):
    type: str


class AuthenticationSucceeded(Event):
    type: Literal["authentication"] = "authentication"
    status: str = "success"
    detail: str | None = None


class AuthenticationFailed(AuthenticationSucceeded):
    status: str = "failure"


class UserCreated(Event):
    type: Literal["user"] = "user"
    id: int
    name: str


class ServiceCreated(Event):
    type: Literal["service"] = "service"
    id: int
    name: str
    data: dict = {}
    deleted: bool = False


class ServiceUpdated(ServiceCreated): ...


class ServiceDeleted(ServiceCreated):
    deleted: bool = True


class StepProcessed(Event):
    type: Literal["step"] = "step"
    id: int
    name: str
    state: Literal["pending", "running", "success", "failure"]
    deployment_id: int
    message: str
    started: datetime | None
    finished: datetime | None
    deleted: bool = False


class StepDeleted(StepProcessed):
    deleted: bool = True


class DeploymentStarted(Event):
    type: Literal["deployment"] = "deployment"
    id: int
    service_id: int
    origin: str
    user: str
    started: datetime
    finished: datetime | None
    context: dict = {}


class DeploymentFinished(DeploymentStarted):
    finished: datetime
