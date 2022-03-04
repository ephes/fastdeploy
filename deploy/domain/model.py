from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, SQLModel

from . import events


class User:
    """
    User model used for authentication.
    """

    id: int | None
    name: str | None
    password: str | None

    def __init__(self, *, id=None, name=None, password=None):
        self.id = id
        self.name = name
        self.password = password

    def __repr__(self):
        return f"User(id={self.id}, name={self.name})"

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "password": self.password,
        }


class PydanticUser(SQLModel, table=True):
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


class Service:
    def __init__(self, *, id=None, name: str = "", data={}):
        self.id = id
        self.name = name
        self.data = data
        self.events = []  # type: list[events.Event]

    def __repr__(self):
        return f"Service(id={self.id}, name={self.name})"

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "data": self.data,
        }

    def delete(self):
        self.events.append(events.ServiceDeleted(id=self.id))


class ServicePydantic(SQLModel, table=True):
    """
    Services are deployed. They have a name and a config (which is a JSON)
    and reflected in the data attribute. They also need to have a script
    which is called to deploy them called 'deploy_script' in data.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    data: dict = Field(sa_column=Column(JSON), default={})

    async def get_steps(self) -> list[StepBase]:
        """
        Get all deployment steps for this service that probably have to
        to be executed. It's not really critical to be 100% right here,
        because it's only used for visualization.
        """
        from .database import repository

        assert self.id is not None
        last_successful_deployment_id = await repository.get_last_successful_deployment_id(self.id)
        if last_successful_deployment_id is not None:
            # try to get steps from last successful deployment
            past_steps = await repository.get_steps_by_deployment_id(last_successful_deployment_id)
            steps = [StepBase(name=step.name) for step in past_steps]
        else:
            # try to get steps from config
            steps = [StepBase(**step) for step in self.data.get("steps", [])]
        if len(steps) == 0:
            # if no steps are found, create a default placeholder step
            steps = [StepBase(name="Unknown step")]
        return steps

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


class DeploymentContext(SQLModel):
    """
    Pass some context for a deployment. For example when deploying a new
    podcast, we need to pass the domain name and the port of the application
    server.
    """

    env: dict = {}


class Deployment(SQLModel, table=True):
    """
    Representing a single deployment for a service. It has an origin
    to indicate who started the deployment (GitHub, Frontend, etc..),
    a context passed to the deployment script and a list of steps.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    service_id: int = Field(foreign_key="service.id")
    origin: str = Field(sa_column=Column("origin", String))
    user: str = Field(sa_column=Column("user", String))
    started: Optional[datetime] = Field(
        default=None,
        sa_column=Column("started", DateTime),
    )
    finished: Optional[datetime] = Field(
        default=None,
        sa_column=Column("finished", DateTime),
    )
    context: dict = Field(sa_column=Column(JSON), default={})

    async def process_step(self, step: Step) -> Step:
        """
        After a deployment step has finished, the result has to be processed.

        * Find out whether the step is already known
        * If it's a known pending step, update the step
        * If it's unknown, create a new step
        * Determine which step is now running
        """
        if self.started is None:
            raise ValueError("deployment has not started yet")

        if self.finished is not None:
            raise ValueError("deployment has already finished")

        from .database import repository

        assert self.id is not None
        steps = await repository.get_steps_by_deployment_id(self.id)

        # find out whether the step is already known
        known_step = None
        running_steps = [step for step in steps if step.state == "running"]
        for running_step in running_steps:
            if running_step.name == step.name:
                known_step = running_step
                break

        pending_steps = [step for step in steps if step.state == "pending"]
        if known_step is None:
            # finished step was not already running -> maybe it was pending?
            for pending_step in pending_steps:
                if pending_step.name == step.name:
                    known_step = pending_step
                    break
        else:
            # finished step was already running -> change state of next pending
            # step to running unless currently finished step has failed
            if len(pending_steps) > 0 and step.state != "failure":
                next_pending_step = pending_steps[0]
                next_pending_step.state = "running"
                await repository.update_step(next_pending_step)

        if known_step is None:
            # if it's an unknown step, create a new step
            step.finished = datetime.now(timezone.utc)
            step.deployment_id = self.id
            return await repository.add_step(step)
        else:
            # if it's a known step, update it
            known_step.started = step.started
            known_step.finished = datetime.now(timezone.utc)
            known_step.state = step.state
            known_step.message = step.message
            return await repository.update_step(known_step)


class DeploymentOut(Deployment):
    """
    Additional type and deleted attributes to make it easier to identify
    deployments via websocket and determine whether they should be deleted.
    """

    type: str = "deployment"
    deleted: bool = False
    details: str | None = None
