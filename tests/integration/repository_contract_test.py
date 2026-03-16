from datetime import datetime, timedelta, timezone

import pytest

from deploy.domain import model

pytestmark = pytest.mark.asyncio


async def assert_repository_contract_returns_plain_models(uow, user_in_db, service_in_db, deployment_in_db):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    finished = started + timedelta(minutes=1)
    previous_deployment = model.Deployment(
        service_id=service_in_db.id,
        origin="github",
        user="fastdeploy",
        started=started,
        finished=finished,
        context={},
    )
    latest_deployment = model.Deployment(
        service_id=service_in_db.id,
        origin="github",
        user="fastdeploy",
        started=finished,
        finished=finished + timedelta(minutes=1),
        context={},
    )
    step = model.Step(name="repository step", deployment_id=deployment_in_db.id)
    deployed_service = model.DeployedService(deployment_id=deployment_in_db.id, config={"foo": "bar"})
    previous_step = model.Step(
        name="first successful step",
        state="success",
        started=started,
        finished=finished,
    )
    latest_step = model.Step(
        name="second successful step",
        state="success",
        started=finished,
        finished=finished + timedelta(minutes=1),
    )

    async with uow:
        await uow.deployments.add(previous_deployment)
        await uow.deployments.add(latest_deployment)
        await uow.commit()
        previous_step.deployment_id = previous_deployment.id
        latest_step.deployment_id = latest_deployment.id
        await uow.steps.add(step)
        await uow.steps.add(previous_step)
        await uow.steps.add(latest_step)
        await uow.deployed_services.add(deployed_service)
        await uow.commit()

    async with uow:
        service = await uow.services.get(service_in_db.id)
        service_by_name = await uow.services.get_by_name(service_in_db.name)
        services = await uow.services.list()
        user = await uow.users.get(user_in_db.name)
        users = await uow.users.list()
        deployment = await uow.deployments.get(deployment_in_db.id)
        deployments = await uow.deployments.get_by_service(service_in_db.id)
        all_deployments = await uow.deployments.list()
        loaded_step = await uow.steps.get(step.id)
        steps = await uow.steps.get_steps_by_deployment(deployment_in_db.id)
        all_steps = await uow.steps.list()
        deployed_services = await uow.deployed_services.list()
        last_successful_deployment_id = await uow.deployments.get_last_successful_deployment_id(service_in_db.id)

    assert isinstance(service, model.Service)
    assert isinstance(service_by_name, model.Service)
    assert all(isinstance(item, model.Service) for item in services)
    assert isinstance(user, model.User)
    assert all(isinstance(item, model.User) for item in users)
    assert isinstance(deployment, model.Deployment)
    assert all(isinstance(item, model.Deployment) for item in deployments)
    assert all(isinstance(item, model.Deployment) for item in all_deployments)
    assert isinstance(loaded_step, model.Step)
    assert all(isinstance(item, model.Step) for item in steps)
    assert all(isinstance(item, model.Step) for item in all_steps)
    assert all(isinstance(item, model.DeployedService) for item in deployed_services)
    assert last_successful_deployment_id == latest_deployment.id


async def test_sqlalchemy_repositories_return_plain_models(uow, user_in_db, service_in_db, deployment_in_db):
    await assert_repository_contract_returns_plain_models(uow, user_in_db, service_in_db, deployment_in_db)


@pytest.mark.db("in_memory")
async def test_in_memory_repositories_return_plain_models(uow, user_in_db, service_in_db, deployment_in_db):
    await assert_repository_contract_returns_plain_models(uow, user_in_db, service_in_db, deployment_in_db)
