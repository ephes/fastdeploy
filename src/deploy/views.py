"""
Readonly views.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from sqlalchemy.exc import NoResultFound
from starlette.concurrency import run_in_threadpool

from .adapters.filesystem import AbstractFilesystem
from .config import settings
from .domain import model
from .service_layer import unit_of_work

DEPLOYMENT_ACTIVITY_BATCH_SIZE = 50
ORPHAN_RECONCILE_BATCH_SIZE = 50
ORPHAN_RECONCILE_DELAY = timedelta(seconds=settings.deployment_orphan_reconcile_delay_seconds)
# After the deployment token has expired the deploy task can neither report
# steps nor finish the deployment, so it can no longer hold the service lock.
STALE_DEPLOYMENT_AGE = timedelta(minutes=settings.deployment_access_token_expire_minutes)


def last_deployment_activity(deployment: model.Deployment, steps: list[model.Step]) -> datetime | None:
    """Latest deployment or step activity, or None for a deployment without a start."""
    if deployment.started is None:
        return None
    return model.latest_activity_timestamp(
        deployment.started, *(value for step in steps for value in (step.started, step.finished))
    )


def deployment_is_too_new_for_reconciliation(
    deployment: model.Deployment,
    now: datetime,
    steps: list[model.Step] | None = None,
) -> bool:
    """
    Avoid reconciling deployments that were active recently: brand-new
    deployments during the startup race window, and deployments whose deploy
    task reported its last step but is still finishing the deployment (for
    example while retrying through a short API outage).
    """
    last_activity = last_deployment_activity(deployment, steps or [])
    return _activity_is_recent(last_activity, now)


def _activity_is_recent(last_activity: datetime | None, now: datetime) -> bool:
    return last_activity is None or now - last_activity < ORPHAN_RECONCILE_DELAY


def deployment_is_orphaned(deployment: model.Deployment, steps: list[model.Step], now: datetime) -> bool:
    """
    An unfinished deployment is orphaned when it has no running/pending steps
    and no activity within the reconcile delay. Its deploy task stopped
    reporting without finishing it, so the outcome is unknown.
    """
    if deployment.finished is not None:
        return False
    if deployment_is_too_new_for_reconciliation(deployment, now, steps):
        return False
    return not deployment_has_open_steps(steps)


async def get_user_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork) -> model.User:
    async with uow:
        user = await uow.users.get(name)
    return user


async def service_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork):
    async with uow:
        service = await uow.services.get_by_name(name)
    return service


async def all_synced_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.Service]:
    async with uow:
        from_db = await uow.services.list()
    return from_db


SourceResult = TypeVar("SourceResult")


async def _source_work(function: Callable[[], SourceResult]) -> SourceResult:
    # Shield the framework's bounded thread worker from request cancellation.
    # Keep UoW ownership and the worker token until the source has really retired.
    work = asyncio.create_task(run_in_threadpool(function))
    cancelled = False
    while not work.done():
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            if not cancelled:
                raise
            break
    if cancelled:
        if not work.cancelled():
            work.exception()
        raise asyncio.CancelledError
    return work.result()


async def get_service_names(fs: AbstractFilesystem) -> list[str]:
    return await _source_work(fs.list)


async def get_services_from_filesystem(fs: AbstractFilesystem) -> list[model.Service]:
    configs = await _source_work(fs.get_configs)
    return [model.Service(name=name, data=config) for name, config in configs]


async def get_steps_from_last_deployment(
    service: model.Service, uow: unit_of_work.AbstractUnitOfWork
) -> list[model.Step]:
    steps: list[model.Step] = []
    if service.id is None:
        return steps
    last_successful_deployment_id = await uow.deployments.get_last_successful_deployment_id(service.id)
    if last_successful_deployment_id is not None:
        # try to get steps from last successful deployment
        # a successful deployment has only successful steps, so it never
        # contains the failure step recorded for an orphaned deployment
        steps.extend(await uow.steps.get_steps_by_deployment(last_successful_deployment_id))
    return steps


async def get_steps_to_do_from_service(
    service: model.Service, uow: unit_of_work.AbstractUnitOfWork | None = None
) -> list[model.Step]:
    """
    Get all deployment steps for this service that probably have to
    to be executed. It's not really critical to be 100% right here,
    because it's only used for visualization purposes.
    """

    if uow is not None:
        async with uow:
            steps = await get_steps_from_last_deployment(service, uow)
            if steps:
                # copy steps from old deployment and create new steps
                # beware: do not use old ids, it would overwrite steps
                # from old deployment
                return [model.Step.new_pending_from_old(step) for step in steps]
    # try to get steps from config
    # Only names belong to a plan, including definitions stored before source admission.
    steps = [model.Step(name=step["name"]) for step in service.data.get("steps", [])]
    if len(steps) == 0:
        # if no steps are found, create a default placeholder step
        steps.append(model.Step(name="Unknown step"))
    return steps


async def get_all_deployments(
    uow: unit_of_work.AbstractUnitOfWork,
    *,
    limit: int = 50,
    before_id: int | None = None,
    service_id: int | None = None,
) -> list[model.Deployment]:
    """Get a bounded history page, newest id first."""
    async with uow:
        deployments = await uow.deployments.list(limit=limit, before_id=before_id, service_id=service_id)
    return deployments


class DeploymentNotFound(Exception):
    """Raised when there is no deployment with the requested id."""

    def __init__(self, deployment_id: int):
        super().__init__(f"Deployment {deployment_id} not found")
        self.deployment_id = deployment_id


async def get_deployment_with_steps(deployment_id: int, uow: unit_of_work.AbstractUnitOfWork) -> model.Deployment:
    """Get a deployment with all steps. Raises DeploymentNotFound for an unknown id."""
    async with uow:
        try:
            deployment = await uow.deployments.get(deployment_id)
        except NoResultFound as e:
            raise DeploymentNotFound(deployment_id) from e
        deployment.steps = await uow.steps.get_steps_by_deployment(deployment_id)
    return deployment


async def get_step_page(
    deployment_id: int, uow: unit_of_work.AbstractUnitOfWork, *, limit: int, before_id: int | None = None
) -> list[model.Step]:
    """Read only the requested step rows, without hydrating a deployment's inventory."""
    async with uow:
        try:
            return await uow.deployments.get_step_page(deployment_id, limit=limit, before_id=before_id)
        except NoResultFound as e:
            raise DeploymentNotFound(deployment_id) from e


def deployment_has_open_steps(steps: list[model.Step]) -> bool:
    """Return True if any step indicates the deployment is still active."""
    return any(step.state in model.OPEN_STEP_STATES for step in steps)


def classify_unfinished_deployment(
    deployment: model.Deployment,
    steps: list[model.Step],
    now: datetime,
) -> str:
    """
    Classify an unfinished deployment for the per-service single-flight check.

    - "orphaned": no running/pending steps and no activity within the reconcile
      delay; finished as failed (same rule as the read-path orphan reconciliation).
    - "stale": started longer ago than the deployment token lifetime (or has no
      start time), so the deploy task cannot report or finish anymore. It does
      not block new deployments but is left untouched.
    - "active": anything else. Blocks a new deployment of the same service.
    """
    return classify_unfinished_activity(
        deployment.started,
        last_deployment_activity(deployment, steps) if deployment.finished is None else None,
        deployment_has_open_steps(steps),
        now,
    )


def classify_unfinished_activity(
    started: datetime | None, last_activity: datetime | None, has_open_steps: bool, now: datetime
) -> str:
    started = model.latest_activity_timestamp(started)
    if started is None:
        return "stale"
    if not _activity_is_recent(last_activity, now) and not has_open_steps:
        return "orphaned"
    if (now - started) >= STALE_DEPLOYMENT_AGE:
        return "stale"
    return "active"


async def unfinished_deployment_activity(
    service_id: int, uow: unit_of_work.AbstractUnitOfWork
) -> AsyncIterator[model.UnfinishedDeploymentActivity]:
    after_id = None
    while True:
        page = await uow.deployments.get_unfinished_activity_page(
            service_id, after_id=after_id, limit=DEPLOYMENT_ACTIVITY_BATCH_SIZE
        )
        for activity in page:
            yield activity
        if len(page) < DEPLOYMENT_ACTIVITY_BATCH_SIZE:
            return
        after_id = page[-1].id


async def get_orphaned_unfinished_deployment_ids(
    uow: unit_of_work.AbstractUnitOfWork,
) -> list[int]:
    """
    Return at most 50 oldest orphaned unfinished deployment ids.
    The database filters all step activity before limiting candidates.

    These deployments are reconciled with FinishOrphanedDeployment.
    """
    cutoff = datetime.now(timezone.utc) - ORPHAN_RECONCILE_DELAY
    async with uow:
        return await uow.deployments.get_orphaned_ids(activity_before=cutoff, limit=ORPHAN_RECONCILE_BATCH_SIZE)


async def all_deployed_services(
    uow: unit_of_work.AbstractUnitOfWork, *, limit: int | None = None, before_id: int | None = None
) -> list[model.DeployedService]:
    """Read the deployed-service inventory, optionally bounded by a cursor and limit."""
    async with uow:
        deployed = await uow.deployed_services.list(limit=limit, before_id=before_id)
    return deployed
