import pytest
import pytest_asyncio

from deploy.domain import commands, model

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(loop_scope="function")
async def service_cascade(uow, service_in_db):
    deployment = model.Deployment(service_id=service_in_db.id, origin="github", user="fastdeploy")
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(name="step1", deployment_id=deployment.id)
        await uow.steps.add(step)
        await uow.commit()
    return service_in_db


async def test_deleting_service_deletes_related_deployment_with_steps(bus, service_cascade):
    async with bus.uow as uow:
        deployments = [d for (d,) in await uow.deployments.get_by_service(service_cascade.id)]
        deployment = deployments[0]
        [step] = await uow.steps.get_steps_by_deployment(deployment.id)
    cmd = commands.DeleteService(service_id=service_cascade.id)
    await bus.handle(cmd)
    async with bus.uow as uow:
        assert await uow.steps.get_steps_by_deployment(deployment.id) == []
        await uow.deployments.get_by_service(service_cascade.id) == []
