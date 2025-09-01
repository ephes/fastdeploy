import abc
import json
from datetime import datetime, timezone

from . import events as events_module


class Serializable(abc.ABC):
    @abc.abstractmethod
    def model_dump(self) -> dict:
        raise NotImplementedError


class EventsMixin(Serializable):
    """
    We cannot raise events at arbitrary points in time, because
    for some events, we need to know the id of a model, which will
    only be known after the model has been saved and the transaction
    has been committed.

    So we record events to raise, and raise them only after the
    unit of work exits it's context and calls raise_recorded_events
    for all seen models.
    """

    def _make_sure_recording_attributes_exists(self) -> None:
        """
        Prepare recording of events. Cant set attributes in __init__
        because it wont be called if the model is created by orm.
        """
        if not hasattr(self, "_recorded_events"):
            self._recorded_events: list[tuple[Serializable, type[events_module.Event]]] = []
        if not hasattr(self, "events"):
            self.events: list[events_module.Event] = []

    def raise_recorded_events(self):
        self._make_sure_recording_attributes_exists()
        for instance, event_cls in self._recorded_events:
            self.events.append(event_cls(**instance.model_dump()))
        self._recorded_events = []  # really important to avoid busy looping

    def record(self, event_cls: type[events_module.Event]):
        """
        Record event to raise later on.
        """
        self._make_sure_recording_attributes_exists()
        self._recorded_events.append((self, event_cls))


class User(EventsMixin):
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

    def __eq__(self, other):
        return self.id == other.id and self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def model_dump(self):
        return {
            "id": self.id,
            "name": self.name,
            "password": self.password,
        }

    def create(self):
        """
        Record created event.
        """
        self.record(events_module.UserCreated)


class Step(EventsMixin):
    """
    Base class for all deployment steps. All steps have a name.
    They can also have started and finished timestamps, depending on
    whether they have been started or finished.
    """

    id: int | None
    name: str
    deployment_id: int | None

    def __init__(
        self, *, id=None, name, started=None, finished=None, state="pending", message="", deployment_id=None, **kwargs
    ):
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
        return f"Step(id={self.id}, name={self.name}, state={self.state}, deployment={self.deployment_id})"

    def __hash__(self):
        return hash((self.name, self.deployment_id, self.started))

    @classmethod
    def new_pending_from_old(cls, other):
        """Last successful steps have to be re-created to be able to be used in a new deployment."""
        reset_attributes = {"id": None, "state": "pending", "started": None, "finished": None}
        return cls(**(other.model_dump() | reset_attributes))

    def model_dump(self):
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
        data = self.model_dump()
        for key in ("started", "finished"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return json.dumps(data)

    def delete(self):
        """Record deleted event."""
        self.record(events_module.StepDeleted)

    def process(self):
        """
        Record processed event.
        """
        self.record(events_module.StepProcessed)

    def start(self):
        """
        Change state to 'running' and set started timestamp.
        """
        self.state = "running"
        self.started = datetime.now(timezone.utc)


class Service(EventsMixin):
    """
    Services are deployed. They have a name and a config (which is a JSON)
    and reflected in the data attribute. They also need to have a script
    which is called to deploy them called 'deploy_script' in data.
    """

    id: int | None
    name: str
    user: str = ""  # str instead of fk because of transport via service token
    origin: str = ""

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

    def model_dump(self):
        return {
            "id": self.id,
            "name": self.name,
            "data": self.data,
        }

    def delete(self):
        """Record deleted event."""
        self.record(events_module.ServiceDeleted)

    def update(self):
        """Record updated event."""
        self.record(events_module.ServiceUpdated)

    def get_deploy_script(self) -> str:
        deploy_script = self.data.get("deploy_script", "deploy.sh")
        deploy_script = deploy_script.replace("/", "")
        return f"{self.name}/{deploy_script}"


class Deployment(EventsMixin):
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

    def model_dump(self):
        if not hasattr(self, "steps"):
            steps = []
        else:
            steps = [step.model_dump() for step in self.steps]
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

        # raise processed events for all modified steps
        for step in modified_steps:
            step.process()
        return modified_steps

    def start_deployment_task(self, service: Service):
        """
        Start actual deployment task and raise started event.
        """
        if self.started is None or self.finished is not None or self.id is None:
            raise ValueError("Unable to start deployment")

        # start first step immediately + raise processed events for all steps
        self.steps[0].start()
        for step in self.steps:
            step.deployment_id = self.id
            step.process()

        # start the deployment task
        from ..tasks import get_deploy_environment, run_deploy

        environment = get_deploy_environment(self, service.get_deploy_script())
        run_deploy(environment)  # subprocess.Popen(...)

        # record started event
        self.record(events_module.DeploymentStarted)

    def finish(self):
        """
        Set finished timestamp, record finished event and
        return all steps that have to be removed.
        """
        self.finished = datetime.now(timezone.utc)
        self.record(events_module.DeploymentFinished)

        steps_to_remove = []
        for step in self.steps:
            if step.state in ("running", "pending"):
                steps_to_remove.append(step)
                step.delete()
        return steps_to_remove


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
                target_service.update()
        else:
            # service does not exist in target, add it
            updated_services.append(service)
            service.update()

    # check if any services in target are not in source
    deleted_services = []
    source_name_lookup = {service.name: service for service in source_services}
    for service in target_services:
        if service.name not in source_name_lookup:
            deleted_services.append(service)
            service.delete()
    return updated_services, deleted_services


class DeployedService(EventsMixin):
    """
    A deployed service is a service that has been deployed with a
    specific config and is now running.
    For example assume there's a podcast service that can be configures
    with a domain name. Then a DeployedService would be a specific
    podcast running on this configured domain.
    """

    id: int | None
    deployment_id: int
    config: dict

    def __init__(self, *, id=None, deployment_id: int, config: dict = {}):
        self.id = id
        self.deployment_id = deployment_id
        self.config = config

    def model_dump(self):
        return {
            "id": self.id,
            "deployment_id": self.deployment_id,
            "config": self.config,
        }

    def __repr__(self):
        return f"DeployedService(id={self.id}, deployment_id={self.deployment_id})"

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.deployment_id)
