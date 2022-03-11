from datetime import datetime

from pydantic import BaseModel


class Event(BaseModel):
    pass


class UserCreated(Event):
    user_id: int
    username: str


class ServiceCreated(Event):
    id: int
    name: str
    data: dict = {}


class ServiceDeleted(Event):
    service_id: int
    name: str


class StepDeleted(Event):
    id: int


class StepProcessed(Event):
    name: str
    deployment_id: int
    state: str
    started: datetime
    finished: datetime
    message: str


class DeploymentStarted(Event):
    service_id: int
    started: datetime


class DeploymentFinished(Event):
    id: int
    finished: datetime
