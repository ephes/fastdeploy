from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from deploy.domain import events, model
from deploy.service_layer.unit_of_work import AbstractUnitOfWork

pytestmark = pytest.mark.asyncio


@pytest.fixture
def deployment():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    return model.Deployment(service_id=1, origin="GitHub", user="foobar", started=started)


@pytest.fixture
def step():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    finished = started + timedelta(minutes=3)
    return model.Step(name="step from database", started=started, finished=finished, state="failure")


# test domain.model.Deployment.process_step


async def test_not_started_deployment_cannot_process_steps(deployment, step):
    deployment.started = None
    with pytest.raises(ValueError):
        await deployment.process_step(step)


async def test_finished_deployment_cannot_process_steps(deployment, step):
    deployment.finished = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        await deployment.process_step(step)


async def test_deployment_process_unknown_step(deployment):
    unknown_step = model.Step(id=1, name="Unknown step", deployment_id=deployment.id, state="success")
    modified_steps = deployment.process_step(unknown_step)
    assert unknown_step in modified_steps


async def test_deployment_process_known_running_step(deployment):
    known_step = model.Step(
        id=1, name="known step", started=datetime.now(timezone.utc), deployment_id=deployment.id, state="running"
    )
    finished_step = model.Step(**(known_step.model_dump() | {"state": "success"}))
    deployment.steps = [known_step]
    modified_steps = deployment.process_step(finished_step)
    assert [finished_step] == modified_steps


async def test_deployment_finish_is_idempotent():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    deployment = model.Deployment(
        id=1,
        service_id=1,
        origin="GitHub",
        user="foobar",
        started=started,
        finished=None,
        steps=[model.Step(id=1, name="step-1", deployment_id=1, state="running")],
    )

    removed_once = deployment.finish()
    finished_once = deployment.finished
    removed_twice = deployment.finish()

    assert len(removed_once) == 1
    assert removed_twice == []
    assert deployment.finished == finished_once


class ModelWithEvents(model.EventsMixin):
    def model_dump(self):
        return {"id": 1, "name": "test"}


async def test_events_mixin_creates_events_on_demand():
    instance = ModelWithEvents()
    instance.record(events.UserCreated)
    instance.raise_recorded_events()
    assert instance.events == [events.UserCreated(**ModelWithEvents().model_dump())]


async def test_events_mixin_events_are_consumable_by_unit_of_work():
    instance = ModelWithEvents()
    instance.record(events.UserCreated)

    class Repository:
        def __init__(self, seen):
            self.seen = seen

    class Uow(AbstractUnitOfWork):
        services: Any = Repository(set())
        deployments: Any = Repository(set())
        steps: Any = Repository(set())
        users: Any = Repository({instance})

        async def _commit(self):
            pass

        async def rollback(self):
            pass

    uow = Uow()
    assert list(uow.collect_new_events()) == [events.UserCreated(**ModelWithEvents().model_dump())]


async def test_default_containers_are_not_shared_between_instances():
    first = model.Deployment(service_id=1, origin="GitHub", user="foobar")
    second = model.Deployment(service_id=1, origin="GitHub", user="foobar")
    first.steps.append(model.Step(name="step"))
    first.context["key"] = "value"
    assert second.steps == []
    assert second.context == {}

    first_service, second_service = model.Service(name="a"), model.Service(name="b")
    first_service.data["key"] = "value"
    assert second_service.data == {}

    first_deployed, second_deployed = model.DeployedService(deployment_id=1), model.DeployedService(deployment_id=2)
    first_deployed.config["key"] = "value"
    assert second_deployed.config == {}


# test domain.model.Deployment.finish_as_orphaned


async def test_finish_as_orphaned_adds_failure_step_with_reason():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    reported = model.Step(id=1, name="step-1", deployment_id=1, state="success", started=started, finished=started)
    open_step = model.Step(id=2, name="step-2", deployment_id=1, state="pending")
    deployment = model.Deployment(
        id=1, service_id=1, origin="GitHub", user="foobar", started=started, steps=[reported, open_step]
    )

    removed, failure_step = deployment.finish_as_orphaned()

    assert deployment.finished is not None
    assert removed == [open_step]
    assert failure_step is not None
    assert failure_step.name == model.ORPHANED_STEP_NAME
    assert failure_step.state == "failure"
    assert failure_step.deployment_id == 1
    assert failure_step.message == model.ORPHANED_STEP_MESSAGE
    assert failure_step.started is not None and failure_step.finished is not None
    assert deployment.steps == [reported, failure_step]
    # the failure step is broadcast like a reported step, once it has been saved
    failure_step.id = 3
    failure_step.raise_recorded_events()
    assert [type(event) for event in failure_step.events] == [events.StepProcessed]


async def test_finish_as_orphaned_on_finished_deployment_is_noop():
    started = datetime.now(timezone.utc) - timedelta(days=1)
    deployment = model.Deployment(id=1, service_id=1, origin="GitHub", user="foobar", started=started)
    deployment.finish()
    finished = deployment.finished

    assert deployment.finish_as_orphaned() == ([], None)
    assert deployment.finished == finished
    assert deployment.steps == []


# test repeated step reports (the response to a processed report got lost)


def make_running_deployment(steps):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    return model.Deployment(id=1, service_id=1, origin="GitHub", user="foobar", started=started, steps=steps)


def make_report(name, started, state="success", message=""):
    return model.Step(
        name=name, started=started, finished=started + timedelta(seconds=5), state=state, message=message
    )


async def test_repeated_report_of_known_step_is_idempotent():
    build = model.Step(id=1, name="build", deployment_id=1, state="running")
    test = model.Step(id=2, name="test", deployment_id=1, state="pending")
    publish = model.Step(id=3, name="publish", deployment_id=1, state="pending")
    deployment = make_running_deployment([build, test, publish])
    started = datetime.now(timezone.utc)

    assert deployment.process_step(make_report("build", started)) == [test, build]
    assert [step.state for step in deployment.steps] == ["success", "running", "pending"]
    finished_once = build.finished

    # the same report again: nothing to insert or update, next step advanced only once
    assert deployment.process_step(make_report("build", started)) == []
    assert [step.state for step in deployment.steps] == ["success", "running", "pending"]
    assert build.finished == finished_once


async def test_repeated_report_of_unknown_step_is_idempotent():
    deployment = make_running_deployment([])
    started = datetime.now(timezone.utc)
    first = make_report("gather facts", started, message="ok")
    deployment.steps = deployment.process_step(first)
    assert deployment.steps == [first]

    assert deployment.process_step(make_report("gather facts", started, message="ok")) == []


@pytest.mark.parametrize("changed", [{"state": "failure"}, {"message": "something else"}])
async def test_conflicting_repeated_report_is_rejected(changed):
    build = model.Step(id=1, name="build", deployment_id=1, state="running")
    test = model.Step(id=2, name="test", deployment_id=1, state="pending")
    deployment = make_running_deployment([build, test])
    started = datetime.now(timezone.utc)
    deployment.process_step(make_report("build", started, message="built"))

    conflicting = make_report("build", started, **({"message": "built"} | changed))
    with pytest.raises(model.StepReportConflict):
        deployment.process_step(conflicting)
    assert (build.state, build.message, test.state) == ("success", "built", "running")


async def test_steps_sharing_a_name_are_not_repeated_reports():
    """Same name but another started timestamp is another step, planned or not."""
    first = model.Step(id=1, name="restart", deployment_id=1, state="running")
    second = model.Step(id=2, name="restart", deployment_id=1, state="pending")
    deployment = make_running_deployment([first, second])
    started = datetime.now(timezone.utc)

    assert deployment.process_step(make_report("restart", started)) == [second, first]
    # a retry of the first report must not consume the second planned step
    assert deployment.process_step(make_report("restart", started)) == []
    assert second.state == "running"

    later = started + timedelta(seconds=1)
    assert deployment.process_step(make_report("restart", later)) == [second]
    assert (second.state, second.started) == ("success", later)

    # an unplanned third step of that name is still added
    third = make_report("restart", later + timedelta(seconds=1))
    assert deployment.process_step(third) == [third]
