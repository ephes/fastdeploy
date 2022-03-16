from datetime import datetime

from fastapi import Depends
from pydantic import BaseModel

from ..bootstrap import get_bus
from ..service_layer.messagebus import MessageBus


class StepBase(BaseModel):
    name: str
    state: str
    started: datetime | None
    finished: datetime | None
    message: str


class Step(StepBase):
    id: int
    deployment_id: int


class StepResult(StepBase):
    started: datetime
    finished: datetime


class Deployment(BaseModel):
    id: int
    service_id: int
    origin: str
    user: str
    started: datetime | None
    finished: datetime | None
    context: dict


class DeploymentWithSteps(Deployment):
    steps: list[Step] = []


class DeploymentWithDetailsUrl(Deployment):
    details: str


class Bus(MessageBus):
    def __init__(self, bus: MessageBus = Depends(get_bus)):
        self.uow = bus.uow
        self.cm = bus.cm
        self.fs = bus.fs
        self.event_handlers = bus.event_handlers
        self.command_handlers = bus.command_handlers
