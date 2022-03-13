import logging

from datetime import datetime, timezone
from typing import Callable, Type

from .. import views
from ..adapters.filesystem import AbstractFilesystem
from ..domain import commands, events, model
from ..service_layer.unit_of_work import AbstractUnitOfWork


logger = logging.getLogger(__name__)


async def create_user(command: commands.CreateUser, uow: AbstractUnitOfWork):
    user = model.User(name=command.username, password=command.password_hash)
    async with uow:
        await uow.users.add(user)
        await uow.commit()
        user.create()


async def delete_service(command: commands.DeleteService, uow: AbstractUnitOfWork):
    async with uow:
        [service] = await uow.services.get(command.service_id)
        await uow.services.delete(service)
        await uow.commit()
        service.delete()


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
        # raise events
        for service in updated_services:
            service.update()
        for service in deleted_services:
            service.delete()


async def finish_deployment(command: commands.FinishDeployment, uow: AbstractUnitOfWork):
    """
    Finish a deployment.

    We set the finished timestamp on the server side because it should not be
    possible to update any deployment attributes.

    * Set the finished timestamp
    * Remove all steps in state "running" or "pending"
    """
    async with uow:
        [deployment] = await uow.deployments.get(command.id)
        deployment.finished = datetime.now(timezone.utc)
        await uow.deployments.add(deployment)

        steps = await uow.steps.get_steps_from_deployment(command.id)
        removed_steps = []
        for (step,) in steps:
            if step.state in ("running", "pending"):
                await uow.steps.delete(step)
                removed_steps.append(step)

        await uow.commit()

        # raise events after commit to have IDs
        for step in removed_steps:
            step.delete()
        deployment.finish()


async def start_deployment(command: commands.StartDeployment, uow: AbstractUnitOfWork):
    """
    Start a deployment. The list of deployment steps is fetched from the
    configuration of the service to deploy or the last successful deployment.
    """
    # get the service that we are deploying from database
    async with uow:
        [service] = await uow.services.get(command.service_id)

    # look up the deployment steps from last deployment
    steps = await views.get_steps_to_do_from_service(service, uow)

    # create a new deployment
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
        await uow.deployments.add(deployment)
        deployment.steps[0].state = "running"  # first step is running
        # have to commit early to get the deployment ID :(
        # FIXME: this is a bit of a hack
        await uow.commit()
        for step in steps:
            step.deployment_id = deployment.id  # set the deployment id fk
            await uow.steps.add(step)

        # save the steps to the database
        await uow.commit()

        # start actual deployment task + raise events
        deployment.start(service)
        for step in steps:
            step.create()


async def process_step(command: commands.ProcessStep, uow: AbstractUnitOfWork):
    """
    Process a finished deployment step.
    """
    # get the deployment that we are deploying from database
    step = model.Step(**command.dict())
    async with uow:
        deployment = await views.get_deployment_with_steps(command.deployment_id, uow)
        steps_to_update = deployment.process_step(step)
        print("process step for deployment: ", deployment)
        print("steps to update: ", steps_to_update)
        for step in steps_to_update:
            await uow.steps.add(step)
        await uow.commit()

        # raise processed events after commit to have IDs
        for step in steps_to_update:
            step.process()


PUBLISH_EVENTS = events.ServiceDeleted | events.DeploymentStarted | events.DeploymentFinished | events.StepDeleted


async def publish_event(event: PUBLISH_EVENTS, publish: Callable):
    logger.info(f"Publishing event {event}")
    await publish("broadcast", event)


EVENT_HANDLERS = {
    events.ServiceDeleted: [publish_event],
    events.ServiceUpdated: [publish_event],
    events.DeploymentFinished: [publish_event],
    events.DeploymentStarted: [publish_event],
    events.StepDeleted: [publish_event],
    events.StepProcessed: [publish_event],
    events.StepCreated: [publish_event],
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
