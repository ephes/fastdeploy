from datetime import datetime
from typing import Literal

from pydantic import BaseModel


EVENT_TYPES = Literal["authentication", "service", "step", "deployment", "user"]


class Event(BaseModel):
    # FIXME use Literal["service", ...] but it does not work
    # in base class with pydantic atm dunno why
    type: str


class AuthenticationSucceeded(Event):
    type: EVENT_TYPES = "authentication"
    status: str = "success"
    detail: str | None = None


class AuthenticationFailed(AuthenticationSucceeded):
    status: str = "failure"


class UserCreated(Event):
    type: EVENT_TYPES = "user"
    id: int
    username: str


class ServiceCreated(Event):
    type: EVENT_TYPES = "service"
    id: int
    name: str
    data: dict = {}
    deleted: bool = False


class ServiceUpdated(ServiceCreated):
    ...


class ServiceDeleted(ServiceCreated):
    deleted: bool = True


class StepProcessed(Event):
    type: EVENT_TYPES = "step"
    id: int
    name: str
    state: Literal["pending", "running", "success", "failure"]
    deployment_id: int
    message: str
    started: datetime
    finished: datetime
    deleted: bool = False


class StepDeleted(StepProcessed):
    deleted: bool = True


class DeploymentStarted(Event):
    type: EVENT_TYPES = "deployment"
    id: int
    service_id: int
    origin: str
    user: str
    started: datetime
    finished: datetime | None


class DeploymentFinished(DeploymentStarted):
    finished: datetime
