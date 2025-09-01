import logging
from collections.abc import Callable
from datetime import datetime, timezone

from .. import views
from ..adapters.filesystem import AbstractFilesystem
from ..domain import commands, events, model
from ..service_layer.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)


async def create_user(command: commands.CreateUser, uow: AbstractUnitOfWork):
    user = model.User(name=command.username, password=command.password_hash)
    async with uow:
        await uow.users.add(user)
        user.create()
        await uow.commit()


async def delete_service(command: commands.DeleteService, uow: AbstractUnitOfWork):
    async with uow:
        [service] = await uow.services.get(command.service_id)
        await uow.services.delete(service)
        service.delete()
        await uow.commit()


async def sync_services(command: commands.SyncServices, uow: AbstractUnitOfWork, fs: AbstractFilesystem):
    """Orchestrate the sync of services between filesystem and database."""

    async def persist_synced_services(uow, updated_services, deleted_services):
        for to_delete in deleted_services:
            if to_delete.id is not None:
                await uow.services.delete(to_delete)
        for to_update in updated_services:
            await uow.services.add(to_update)

    target_services = await views.all_synced_services(uow)
    source_services = await views.get_services_from_filesystem(fs)

    updated_services, deleted_services = model.sync_services(source_services, target_services)
    async with uow:
        await persist_synced_services(uow, updated_services, deleted_services)
        await uow.commit()


async def finish_deployment(command: commands.FinishDeployment, uow: AbstractUnitOfWork):
    """
    Finish a deployment.

    Get steps from deployment that have to be removed, because they
    where still running or pending. Remove those steps from the database
    and update the finished deployment.
    """
    async with uow:
        deployment = await views.get_deployment_with_steps(command.deployment_id, uow)
        removed_steps = deployment.finish()
        for step in removed_steps:
            await uow.steps.delete(step)
        await uow.deployments.add(deployment)
        await uow.commit()


async def start_deployment(command: commands.StartDeployment, uow: AbstractUnitOfWork):
    """
    Start a deployment. The list of deployment steps is fetched from the
    configuration of the service to deploy or the last successful deployment.
    """
    # get the service that we are deploying from database
    async with uow:
        [service] = await uow.services.get(command.service_id)

    # look up the deployment steps from last deployment / service.data / default
    # and create new deployment
    steps = await views.get_steps_to_do_from_service(service, uow)
    deployment = model.Deployment(
        service_id=command.service_id,
        origin=command.origin,
        user=command.user,
        context=command.context,
        started=datetime.now(timezone.utc),
        finished=None,
        steps=steps,
    )

    # actually start the deployment
    async with uow:
        # add the deployment to the database
        # have to commit early to get the deployment ID :(
        # FIXME: this is a bit of a hack
        await uow.deployments.add(deployment)
        await uow.commit()

        # start deployment task
        deployment.start_deployment_task(service)
        for step in deployment.steps:
            await uow.steps.add(step)
        await uow.commit()


async def process_step(command: commands.ProcessStep, uow: AbstractUnitOfWork):
    """
    Process a finished deployment step.
    """
    # get the deployment that we are deploying from database
    step = model.Step(**command.model_dump())
    async with uow:
        deployment = await views.get_deployment_with_steps(command.deployment_id, uow)
        steps_to_update = deployment.process_step(step)
        for step in steps_to_update:
            await uow.steps.add(step)
        await uow.commit()


PUBLISH_EVENTS = events.ServiceDeleted | events.DeploymentStarted | events.DeploymentFinished | events.StepDeleted


async def publish_event(event: PUBLISH_EVENTS, publish: Callable):
    logger.info(f"Publishing event {event}")
    await publish("broadcast", event)


async def update_deployed_services(event: events.DeploymentFinished):
    """
    Depending on which service was deployed, add a service to the
    list of deployed services or remove it.
    """
    pass


EVENT_HANDLERS = {
    events.ServiceDeleted: [publish_event],
    events.ServiceUpdated: [publish_event],
    events.DeploymentFinished: [publish_event, update_deployed_services],
    events.DeploymentStarted: [publish_event],
    events.StepDeleted: [publish_event],
    events.StepProcessed: [publish_event],
    events.UserCreated: [],
}  # type: dict[Type[events.Event], list[Callable]]

COMMAND_HANDLERS = {
    commands.CreateUser: create_user,
    commands.DeleteService: delete_service,
    commands.SyncServices: sync_services,
    commands.StartDeployment: start_deployment,
    commands.FinishDeployment: finish_deployment,
    commands.ProcessStep: process_step,
}  # type: dict[Type[commands.Command], Callable]
