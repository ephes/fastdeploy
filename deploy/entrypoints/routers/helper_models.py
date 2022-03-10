from datetime import datetime

from pydantic import BaseModel


class Step(BaseModel):
    id: int
    name: str
    deployment_id: int
    state: str
    started: datetime | None
    finished: datetime | None
    message: str


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
