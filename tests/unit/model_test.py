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
