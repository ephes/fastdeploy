from datetime import datetime

from fastapi import Depends
from pydantic import BaseModel, Field

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


# Limits for reported steps. They are the sizes of the columns of the step
# table, so a longer value could not be stored anyway.
MAX_STEP_NAME_LENGTH = 255
MAX_STEP_STATE_LENGTH = 20
MAX_STEP_MESSAGE_LENGTH = 4096


class StepResult(StepBase):
    """
    A step reported by a deploy task. Only this input model is limited in
    size, the models used for responses are not.
    """

    name: str = Field(max_length=MAX_STEP_NAME_LENGTH)
    state: str = Field(max_length=MAX_STEP_STATE_LENGTH)
    started: datetime
    finished: datetime
    message: str = Field(max_length=MAX_STEP_MESSAGE_LENGTH)


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
