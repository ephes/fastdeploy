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
