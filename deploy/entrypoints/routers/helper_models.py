from datetime import datetime

from pydantic import BaseModel


class StepBase(BaseModel):
    name: str
    state: str
    started: datetime | None
    finished: datetime | None
    message: str


class Step(StepBase):
    id: int


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
