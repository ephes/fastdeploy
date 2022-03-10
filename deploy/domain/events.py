from datetime import datetime

from pydantic import BaseModel


class Event(BaseModel):
    pass


class ServiceCreated(Event):
    id: int
    name: str
    data: dict = {}


class ServiceDeleted(Event):
    id: int
    foo = "service deleted!"


class StepDeleted(Event):
    id: int
    foo = "service deleted!"


class DeploymentStarted(Event):
    service_id: int
    started: datetime


class DeploymentFinished(Event):
    id: int
    finished: datetime
