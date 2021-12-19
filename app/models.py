from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """
    User model used for authentication.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    password: str


class StepBase(SQLModel):
    """
    Base class for all deployment steps. All steps have a unique name.
    They can also have started and finished timestamps, depending on
    whether they have been started or finished.
    """

    name: str
    started: Optional[datetime] = Field(
        default=None,
        sa_column=Column("started", DateTime),
    )
    finished: Optional[datetime] = Field(
        default=None,
        sa_column=Column("finished", DateTime),
    )
    state: str = Field(default="pending", sa_column=Column("state", String))
    message: str = Field(default="", sa_column=Column("message", String))


class Step(StepBase, table=True):
    """
    A step in a deployment process. This is used to store steps in the
    database. If a step is stored in the database, it has to have an
    id and a reference to the deployment it is part of.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    deployment_id: int = Field(foreign_key="deployment.id")


class StepOut(Step):
    """
    Steps which are sent out to the client. If they are received via websocket,
    they need to be identifyable by their type as steps. They also have a
    deleted flag to indicate whether they have been deleted from the database.
    """

    type: str = "step"
    deleted: bool = False

    def dict(self, *args, **kwargs):
        serialized = super().dict(*args, **kwargs)
        return serialized


class Service(SQLModel, table=True):
    """
    Services are deployed. They have a name and a config (which is a JSON)
    and reflected in the data attribute. They also need to have a script
    which is called to deploy them called 'deploy_script' in data.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    data: dict = Field(sa_column=Column(JSON), default={})

    def get_steps(self) -> list[Step]:
        return [Step(**step) for step in self.data.get("steps", [])]

    def get_deploy_script(self) -> str:
        deploy_script = self.data.get("deploy_script", "deploy.sh")
        deploy_script = deploy_script.replace("/", "")
        return f"{self.name}/{deploy_script}"


class ServiceOut(Service):
    """
    Additional type and deleted attributes to make it easier to identify
    them when received via websocket and to decide whether they should be
    added/updated or deleted.
    """

    type: str = "service"
    deleted: bool = False


class Deployment(SQLModel, table=True):
    """
    Representing a single deployment for a service. It has an origin
    to indicate who started the deployment (GitHub, Frontend, etc..)
    and a list of steps which have been executed.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    service_id: int = Field(foreign_key="service.id")
    origin: str = Field(sa_column=Column("origin", String))
    user: str = Field(sa_column=Column("user", String))
    created: Optional[datetime] = Field(
        default=None,
        sa_column=Column("created", DateTime),
    )
    finished: Optional[datetime] = Field(
        default=None,
        sa_column=Column("finished", DateTime),
    )


class DeploymentOut(Deployment):
    """
    Additional type and deleted attributes to make it easier to identify
    deployments via websocket and determine whether they should be deleted.
    """

    type: str = "deployment"
    deleted: bool = False
