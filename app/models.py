from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, Session, SQLModel, select

from . import database


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    password: str


class Service(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))


class Deployment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    service_id: int = Field(foreign_key="service.id")
    origin: str = Field(sa_column=Column("origin", String))
    user: str = Field(sa_column=Column("user", String))
    created: datetime = Field(
        default=datetime.now(timezone.utc),
        sa_column=Column("created", DateTime),
    )


def add_deployment(deployment: Deployment):
    with Session(database.engine) as session:
        session.add(deployment)
        session.commit()
        session.refresh(deployment)


class StepBase(SQLModel):
    name: str


class Step(StepBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    deployment_id: int = Field(foreign_key="deployment.id")
    created: datetime = Field(
        default=datetime.now(timezone.utc),
        sa_column=Column("created", DateTime),
    )


def add_step(step: Step):
    with Session(database.engine) as session:
        session.add(step)
        session.commit()
        session.refresh(step)


def get_step_by_id(step_id):
    with Session(database.engine) as session:
        step = session.exec(select(Step).where(Step.id == step_id)).first()
    return step


def update_step(step: Step):
    add_step(step)
