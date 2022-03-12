import json

from datetime import datetime, timezone
from typing import List

from . import events


class User:
    """
    User model used for authentication.
    """

    id: int | None
    name: str | None
    password: str | None
    events = []  # type: List[events.Event]

    def __init__(self, *, id=None, name=None, password=None):
        self.id = id
        self.name = name
        self.password = password

    def __repr__(self):
        return f"User(id={self.id}, name={self.name})"

    def __eq__(self, other):
        return self.id == other.id and self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "password": self.password,
        }

    def create(self):
        """
        Raise created event.
        """
        assert self.id is not None and self.name is not None
        self.events.append(events.UserCreated(id=self.id, username=self.name))


class Step:
    """
    Base class for all deployment steps. All steps have a name.
    They can also have started and finished timestamps, depending on
    whether they have been started or finished.
    """

    id: int | None
    name: str
    deployment_id: int | None
    events = []  # type: List[events.Event]

    def __init__(self, *, id=None, name, started=None, finished=None, state="pending", message="", deployment_id=None):
        self.id = id
        self.name = name
        self.started = started
        self.finished = finished
        self.state = state
        self.deployment_id = deployment_id
        self.message = message

    def __eq__(self, other):
        return self.id == other.id

    def __repr__(self):
        return f"Step(id={self.id}, name={self.name}, state={self.state})"

    def __hash__(self):
        return hash((self.name, self.deployment_id, self.started))

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "started": self.started,
            "finished": self.finished,
            "state": self.state,
            "deployment_id": self.deployment_id,
            "message": self.message,
        }

    def json(self):
        data = self.dict()
        for key in ("started", "finished"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return json.dumps(data)

    def delete(self):
        """Raise deleted event."""
        assert self.id is not None
        deleted = events.StepDeleted(**self.dict())
        self.events.append(deleted)

    def process(self):
        """
        Raise processed event.
        """
        self.events.append(events.StepProcessed(**self.dict()))

    def create(self):
        """
        Raise created event.
        """
        self.events.append(events.StepCreated(**self.dict()))


# class StepBase(SQLModel):
#     """
#     Base class for all deployment steps. All steps have a unique name.
#     They can also have started and finished timestamps, depending on
#     whether they have been started or finished.
#     """

#     name: str
#     started: Optional[datetime] = Field(
#         default=None,
#         sa_column=Column("started", DateTime),
#     )
#     finished: Optional[datetime] = Field(
#         default=None,
#         sa_column=Column("finished", DateTime),
#     )
#     state: str = Field(default="pending", sa_column=Column("state", String))
#     message: str = Field(default="", sa_column=Column("message", String))


# class PydanticStep(StepBase, table=True):
#     """
#     A step in a deployment process. This is used to store steps in the
#     database. If a step is stored in the database, it has to have an
#     id and a reference to the deployment it is part of.
#     """

#     id: Optional[int] = Field(default=None, primary_key=True)
#     deployment_id: int = Field(foreign_key="deployment.id")


# class StepOut(PydanticStep):
#     """
#     Steps which are sent out to the client. If they are received via websocket,
#     they need to be identifyable by their type as steps. They also have a
#     deleted flag to indicate whether they have been deleted from the database.
#     """

#     type: str = "step"  # noqa: F723
#     deleted: bool = False

#     def dict(self, *args, **kwargs):
#         serialized = super().dict(*args, **kwargs)
#         return serialized


class Service:
    """
    Services are deployed. They have a name and a config (which is a JSON)
    and reflected in the data attribute. They also need to have a script
    which is called to deploy them called 'deploy_script' in data.
    """

    id: int | None
    name: str
    user: str = ""  # str instead of fk because of transport via service token
    origin: str = ""
    events = []  # type: List[events.Event]

    def __init__(self, *, id=None, name: str = "", data={}):
        self.id = id
        self.name = name
        self.data = data

    def __repr__(self):
        return f"Service(id={self.id}, name={self.name})"

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "data": self.data,
        }

    def delete(self):
        """Raise deleted event."""
        assert self.id is not None and self.name is not None
        deleted = events.ServiceDeleted(**self.dict())
        self.events.append(deleted)

    def update(self):
        """Raise updated event."""
        assert self.id is not None and self.name is not None
        updated = events.ServiceUpdated(**self.dict())
        self.events.append(updated)

    def get_deploy_script(self) -> str:
        deploy_script = self.data.get("deploy_script", "deploy.sh")
        deploy_script = deploy_script.replace("/", "")
        return f"{self.name}/{deploy_script}"


# class ServicePydantic(SQLModel, table=True):
#     """
#     Services are deployed. They have a name and a config (which is a JSON)
#     and reflected in the data attribute. They also need to have a script
#     which is called to deploy them called 'deploy_script' in data.
#     """

#     id: Optional[int] = Field(default=None, primary_key=True)
#     name: str = Field(sa_column=Column("name", String, unique=True))
#     data: dict = Field(sa_column=Column(JSON), default={})

#     async def get_steps(self) -> list[StepBase]:
#         """
#         Get all deployment steps for this service that probably have to
#         to be executed. It's not really critical to be 100% right here,
#         because it's only used for visualization.
#         """
#         from .database import repository

#         assert self.id is not None
#         last_successful_deployment_id = await repository.get_last_successful_deployment_id(self.id)
#         if last_successful_deployment_id is not None:
#             # try to get steps from last successful deployment
#             past_steps = await repository.get_steps_by_deployment_id(last_successful_deployment_id)
#             steps = [StepBase(name=step.name) for step in past_steps]
#         else:
#             # try to get steps from config
#             steps = [StepBase(**step) for step in self.data.get("steps", [])]
#         if len(steps) == 0:
#             # if no steps are found, create a default placeholder step
#             steps = [StepBase(name="Unknown step")]
#         return steps

#     def get_deploy_script(self) -> str:
#         deploy_script = self.data.get("deploy_script", "deploy.sh")
#         deploy_script = deploy_script.replace("/", "")
#         return f"{self.name}/{deploy_script}"


class ServiceOut(Service):
    """
    Additional type and deleted attributes to make it easier to identify
    them when received via websocket and to decide whether they should be
    added/updated or deleted.
    """

    type: str = "service"
    deleted: bool = False


class Deployment:
    """
    Representing a single deployment for a service. It has an origin
    to indicate who started the deployment (GitHub, Frontend, etc..),
    a context passed to the deployment script and a list of steps.
    """

    id: int | None
    service_id: int
    origin: str
    user: str
    started: datetime | None
    finished: datetime | None
    context: dict
    steps: list[Step]
    events = []  # type: List[events.Event]

    def __init__(
        self,
        *,
        id=None,
        service_id: int,
        origin: str,
        user: str,
        started: datetime | None = None,
        finished: datetime | None = None,
        context: dict = {},
        steps: list[Step] = [],
    ):
        self.id = id
        self.service_id = service_id
        self.origin = origin
        self.user = user
        self.started = started
        self.finished = finished
        self.context = context
        self.steps = steps

    def dict(self):
        if not hasattr(self, "steps"):
            steps = []
        else:
            steps = [step.dict() for step in self.steps]
        return {
            "id": self.id,
            "service_id": self.service_id,
            "origin": self.origin,
            "user": self.user,
            "started": self.started,
            "finished": self.finished,
            "context": self.context,
            "steps": steps,
        }

    def __repr__(self):
        return f"Deployment(id={self.id}, service_id={self.service_id})"

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash((self.service_id, self.started))

    def process_step(self, step: Step) -> list[Step]:
        """
        After a deployment step has finished, the result has to be processed.
        We need to check whether the current step is in the list of the steps
        we need to take etc.

        Returns a new list of steps that have been modified.

        * Find out whether the step is already known
        * If it's a known pending step, update the pending steps state and add
          to the list of modified steps
        * If it's unknown, add it to the list of modified steps
        * Determine which step is now running and add it to the list
          of modified steps, too
        """
        if self.started is None:
            raise ValueError("deployment has not started yet")

        if self.finished is not None:
            raise ValueError("deployment has already finished")

        steps = self.steps
        modified_steps = []

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
                modified_steps.append(next_pending_step)

        if known_step is None:
            # if it's an unknown step, create a new step
            step.finished = datetime.now(timezone.utc)
            step.deployment_id = self.id
            modified_steps.append(step)
        else:
            # if it's a known step, update it
            known_step.started = step.started
            known_step.finished = datetime.now(timezone.utc)
            known_step.state = step.state
            known_step.message = step.message
            modified_steps.append(known_step)
        return modified_steps

    def start(self, service: Service) -> None:
        """
        Start actual deployment task and raise started event.
        """
        if self.started is None or self.finished is not None or self.id is None:
            raise ValueError("Unable to start deployment")

        # start the deployment task
        from ..tasks import get_deploy_environment, run_deploy

        environment = get_deploy_environment(self, service.get_deploy_script())
        run_deploy(environment)  # subprocess.Popen(...)

        # raise started event
        assert service.id is not None
        print(self.dict())
        started = events.DeploymentStarted(**self.dict())
        self.events.append(started)

    def finish(self):
        """
        Raise finished event.
        """
        assert self.id is not None and self.finished is not None
        finished = events.DeploymentFinished(**self.dict())
        self.events.append(finished)


# class DeploymentPydantic(SQLModel, table=True):
#     """
#     Representing a single deployment for a service. It has an origin
#     to indicate who started the deployment (GitHub, Frontend, etc..),
#     a context passed to the deployment script and a list of steps.
#     """

#     id: Optional[int] = Field(default=None, primary_key=True)
#     service_id: int = Field(foreign_key="service.id")
#     origin: str = Field(sa_column=Column("origin", String))
#     user: str = Field(sa_column=Column("user", String))
#     started: Optional[datetime] = Field(
#         default=None,
#         sa_column=Column("started", DateTime),
#     )
#     finished: Optional[datetime] = Field(
#         default=None,
#         sa_column=Column("finished", DateTime),
#     )
#     context: dict = Field(sa_column=Column(JSON), default={})

#     async def process_step(self, step: Step) -> Step:
#         """
#         After a deployment step has finished, the result has to be processed.

#         * Find out whether the step is already known
#         * If it's a known pending step, update the step
#         * If it's unknown, create a new step
#         * Determine which step is now running
#         """
#         if self.started is None:
#             raise ValueError("deployment has not started yet")

#         if self.finished is not None:
#             raise ValueError("deployment has already finished")

#         from .database import repository

#         assert self.id is not None
#         steps = await repository.get_steps_by_deployment_id(self.id)

#         # find out whether the step is already known
#         known_step = None
#         running_steps = [step for step in steps if step.state == "running"]
#         for running_step in running_steps:
#             if running_step.name == step.name:
#                 known_step = running_step
#                 break

#         pending_steps = [step for step in steps if step.state == "pending"]
#         if known_step is None:
#             # finished step was not already running -> maybe it was pending?
#             for pending_step in pending_steps:
#                 if pending_step.name == step.name:
#                     known_step = pending_step
#                     break
#         else:
#             # finished step was already running -> change state of next pending
#             # step to running unless currently finished step has failed
#             if len(pending_steps) > 0 and step.state != "failure":
#                 next_pending_step = pending_steps[0]
#                 next_pending_step.state = "running"
#                 await repository.update_step(next_pending_step)

#         if known_step is None:
#             # if it's an unknown step, create a new step
#             step.finished = datetime.now(timezone.utc)
#             step.deployment_id = self.id
#             return await repository.add_step(step)
#         else:
#             # if it's a known step, update it
#             known_step.started = step.started
#             known_step.finished = datetime.now(timezone.utc)
#             known_step.state = step.state
#             known_step.message = step.message
#             return await repository.update_step(known_step)


class DeploymentOut(Deployment):
    """
    Additional type and deleted attributes to make it easier to identify
    deployments via websocket and determine whether they should be deleted.
    """

    type: str = "deployment"
    deleted: bool = False
    details: str | None = None


def sync_services(
    source_services: list[Service], target_services: list[Service]
) -> tuple[list[Service], list[Service]]:
    """Compare source and target services and update/delete accordingly"""
    updated_services = []
    target_name_lookup = {service.name: service for service in target_services}
    for service in source_services:
        if service.name in target_name_lookup:
            # service exists in target, check if it needs to be updated
            target_service = target_name_lookup[service.name]
            if target_service.data != service.data:
                # it's sufficient to check if the data is different, because
                # if name differs, it's a new/deleted service
                target_service.data = service.data
                # use target_service to keep the id
                updated_services.append(target_service)
        else:
            # service does not exist in target, add it
            updated_services.append(service)

    # check if any services in target are not in source
    deleted_services = []
    source_name_lookup = {service.name: service for service in source_services}
    for service in target_services:
        if service.name not in source_name_lookup:
            deleted_services.append(service)
    return updated_services, deleted_services
