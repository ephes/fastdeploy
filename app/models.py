from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    password: str


class Service(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    collect: str
    deploy: str


class ServiceOut(Service):
    type: str = "service"
    deleted: bool = False


class Deployment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    service_id: int = Field(foreign_key="service.id")
    origin: str = Field(sa_column=Column("origin", String))
    user: str = Field(sa_column=Column("user", String))
    created: Optional[datetime] = Field(
        default=None,
        sa_column=Column("created", DateTime),
    )


class DeploymentOut(Deployment):
    type: str = "deployment"
    deleted: bool = False


class StepBase(SQLModel):
    name: str
    started: Optional[datetime] = Field(
        default=None,
        sa_column=Column("started", DateTime),
    )
    finished: Optional[datetime] = Field(
        default=None,
        sa_column=Column("finished", DateTime),
    )


class Step(StepBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    deployment_id: int = Field(foreign_key="deployment.id")
    created: Optional[datetime] = Field(
        default=None,
        sa_column=Column("created", DateTime),
    )


class StepOut(Step):
    type: str = "step"
    deleted: bool = False

    def dict(self, *args, **kwargs):
        serialized = super().dict(*args, **kwargs)
        serialized["in_progress"] = self.started is not None and self.finished is None
        serialized["done"] = self.finished is not None
        return serialized
