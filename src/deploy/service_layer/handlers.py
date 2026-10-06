import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

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
        service = await uow.services.get(command.service_id)
        await uow.services.delete(service)
        service.delete()
        await uow.commit()


async def sync_services(
    command: commands.SyncServices, uow: AbstractUnitOfWork, fs: AbstractFilesystem
) -> model.ServiceSyncResult:
    """
    Orchestrate the sync of services between filesystem and database.

    Raises ``ServiceSyncRefused`` (and changes nothing) when the sync would
    delete all or more than half of the services and is not forced. Services
    with an active deployment are never deleted, they are reported as skipped.
    """
    source_services = await views.get_services_from_filesystem(fs)
    now = datetime.now(timezone.utc)
    async with uow:
        target_services = await uow.services.list()
        updated_services, candidates = model.sync_services(source_services, target_services)
        model.check_sync_deletions(source_services, target_services, candidates, command.force)

        deleted: list[model.Service] = []
        skipped: list[model.SkippedService] = []
        # lock in id order, deployment starts lock a single service row
        for service in sorted(candidates, key=lambda s: s.id or 0):
            if service.id is None:
                continue
            # Serialize with deployment starts: a start that already holds the
            # lock has committed its deployment once we get the lock.
            await uow.services.lock_for_deployment(service.id)
            active_ids = await active_deployment_ids(service.id, uow, now)
            if active_ids:
                logger.warning("Not deleting service %s: deployments %s are still running", service.name, active_ids)
                skipped.append(
                    model.SkippedService(name=service.name, reason=f"deployment {active_ids[0]} is still running")
                )
                continue
            await uow.services.delete(service)
            service.delete()
            deleted.append(service)

        for to_update in updated_services:
            await uow.services.add(to_update)
        await uow.commit()

    return model.ServiceSyncResult(
        updated=[service.name for service in updated_services],
        deleted=[service.name for service in deleted],
        skipped=skipped,
    )


async def active_deployment_ids(service_id: int, uow: AbstractUnitOfWork, now: datetime) -> list[int]:
    """
    Return the ids of the deployments of a service that are still running,
    using the same rule as the per-service single-flight check.
    """
    active: list[int] = []
    for unfinished in await uow.deployments.get_unfinished_by_service(service_id):
        if unfinished.id is None:
            continue
        steps = await uow.steps.get_steps_by_deployment(unfinished.id)
        if views.classify_unfinished_deployment(unfinished, steps, now) == "active":
            active.append(unfinished.id)
    return active


async def revoke_service_token(command: commands.RevokeServiceToken, uow: AbstractUnitOfWork) -> model.ServiceToken:
    """Revoke an issued service token by its id (jti)."""
    async with uow:
        # lock the row so concurrent revocations keep the first revoked_at
        service_token = await uow.service_tokens.get_by_jti(command.jti, for_update=True)
        if service_token is None:
            raise model.ServiceTokenNotFound(command.jti)
        service_token.revoke(datetime.now(timezone.utc))
        await uow.service_tokens.add(service_token)
        await uow.commit()
    return service_token


async def purge_service_tokens(command: commands.PurgeServiceTokens, uow: AbstractUnitOfWork) -> int:
    """
    Delete records of service tokens that expired or were revoked more than
    ``retention_days`` ago. Returns the number of deleted records.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=command.retention_days)
    async with uow:
        deleted = await uow.service_tokens.delete_stale(cutoff)
        await uow.commit()
    return deleted


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


async def finish_orphans_or_raise_if_running(service_id: int, uow: AbstractUnitOfWork) -> None:
    """
    Must be called inside an open unit of work, after the service has been
    locked for deployment. Raises ``DeploymentAlreadyRunning`` if the service
    has an active deployment; otherwise finishes its orphaned unfinished
    deployments (staged in the current transaction). Nothing is mutated when
    the start is refused.
    """
    now = datetime.now(timezone.utc)
    orphans: list[tuple[model.Deployment, list[model.Step]]] = []
    for unfinished in await uow.deployments.get_unfinished_by_service(service_id):
        if unfinished.id is None:
            continue
        steps = await uow.steps.get_steps_by_deployment(unfinished.id)
        state = views.classify_unfinished_deployment(unfinished, steps, now)
        if state == "active":
            raise model.DeploymentAlreadyRunning(service_id=service_id, deployment_id=unfinished.id)
        if state == "orphaned":
            orphans.append((unfinished, steps))

    for orphan, steps in orphans:
        logger.info("Finishing orphaned deployment %s before starting a new one", orphan.id)
        orphan.steps = steps
        for step in orphan.finish():
            await uow.steps.delete(step)
        await uow.deployments.add(orphan)


async def start_deployment(command: commands.StartDeployment, uow: AbstractUnitOfWork):
    """
    Start a deployment. The list of deployment steps is fetched from the
    configuration of the service to deploy or the last successful deployment.
    """
    # get the service that we are deploying from database
    async with uow:
        service = await uow.services.get(command.service_id)

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
        # Single-flight per service: lock the service row so concurrent starts
        # for the same service are serialized, reconcile orphaned deployments and
        # refuse if another deployment is still active. The lock is held until
        # the commit below, which also makes the new deployment visible.
        await uow.services.lock_for_deployment(command.service_id)
        await finish_orphans_or_raise_if_running(command.service_id, uow)

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
}  # type: dict[type[events.Event], list[Callable]]

COMMAND_HANDLERS = {
    commands.CreateUser: create_user,
    commands.DeleteService: delete_service,
    commands.SyncServices: sync_services,
    commands.RevokeServiceToken: revoke_service_token,
    commands.PurgeServiceTokens: purge_service_tokens,
    commands.StartDeployment: start_deployment,
    commands.FinishDeployment: finish_deployment,
    commands.ProcessStep: process_step,
}  # type: dict[type[commands.Command], Callable]
