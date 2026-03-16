from datetime import datetime, timedelta, timezone

import pytest

from deploy import views
from deploy.domain import model

pytestmark = pytest.mark.asyncio

# test views.get_steps_to_do_from_service


async def test_get_steps_to_do_from_service_returns_placeholder_step(service):
    steps = await views.get_steps_to_do_from_service(service)
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


async def test_get_steps_to_do_from_service_has_steps_in_data(service):
    step = model.Step(id=1, name="Step 1")
    service.data = {"steps": [step.model_dump()]}
    steps = await views.get_steps_to_do_from_service(service)
    assert [step] == steps


async def test_get_steps_to_do_from_service_only_failure_steps(uow, service_in_db):
    service = service_in_db
    started = datetime.now(timezone.utc) - timedelta(days=1)
    finished = started + timedelta(minutes=3)
    deployment = model.Deployment(
        service_id=service.id, origin="GitHub", user="foobar", started=started, finished=finished
    )
    step = model.Step(name="step from database", started=started, finished=finished, state="failure")
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        step.deployment_id = deployment.id
        await uow.steps.add(step)
        await uow.commit()

    steps = await views.get_steps_to_do_from_service(service, uow=uow)
    assert len(steps) == 1
    assert steps[0].name == "Unknown step"


async def test_get_steps_to_do_from_service_steps_from_last_deployment(uow, service_in_db):
    service = service_in_db
    started = datetime.now(timezone.utc) - timedelta(days=1)
    finished = started + timedelta(minutes=3)
    deployment = model.Deployment(
        service_id=service.id, origin="GitHub", user="foobar", started=started, finished=finished
    )
    step = model.Step(name="step from database", started=started, finished=finished, state="success")
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        step.deployment_id = deployment.id
        await uow.steps.add(step)
        await uow.commit()

    steps = await views.get_steps_to_do_from_service(service, uow=uow)
    assert steps[0].name == "step from database"


class FakeRow:
    def __init__(self, value):
        self._mapping = {"value": value}


class FakeRepo:
    def __init__(self, get_result=None, list_result=None):
        self._get_result = get_result
        self._list_result = list_result or []

    async def get(self, *_args, **_kwargs):
        return self._get_result

    async def get_steps_by_deployment(self, *_args, **_kwargs):
        return self._list_result

    async def list(self):
        return self._list_result


class FakeUow:
    def __init__(self, deployment, steps):
        self.deployments = FakeRepo(get_result=FakeRow(deployment))
        self.steps = FakeRepo(list_result=[FakeRow(step) for step in steps])
        self.services = FakeRepo(list_result=[])
        self.deployed_services = FakeRepo(list_result=[])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


async def test_get_deployment_with_steps_unwraps_sqlalchemy_style_rows():
    deployment = model.Deployment(
        id=1,
        service_id=1,
        origin="echoport",
        user="fastdeploy",
        started=datetime.now(timezone.utc),
    )
    steps = [
        model.Step(id=1, name="init", deployment_id=1, state="running"),
        model.Step(id=2, name="backup", deployment_id=1, state="pending"),
    ]
    uow = FakeUow(deployment=deployment, steps=steps)

    loaded = await views.get_deployment_with_steps(1, uow)

    assert isinstance(loaded, model.Deployment)
    assert all(isinstance(step, model.Step) for step in loaded.steps)
    modified_steps = loaded.process_step(
        model.Step(
            name="init",
            deployment_id=1,
            state="success",
            started=steps[0].started,
            finished=datetime.now(timezone.utc),
            message="done",
        )
    )
    assert {step.name for step in modified_steps} == {"init", "backup"}
    assert next(step for step in modified_steps if step.name == "backup").state == "running"


async def test_normalize_repo_rows_unwraps_sqlalchemy_style_rows():
    service = model.Service(id=1, name="echoport-backup", data={})
    deployed_service = model.DeployedService(id=1, deployment_id=1, config={"foo": "bar"})

    normalized = views._normalize_repo_rows([FakeRow(service), FakeRow(deployed_service)])

    assert normalized == [service, deployed_service]
