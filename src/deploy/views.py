"""
Readonly views.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import NoResultFound

from .adapters.filesystem import AbstractFilesystem
from .config import settings
from .domain import model
from .service_layer import unit_of_work

OPEN_STEP_STATES = {"pending", "running"}
ORPHAN_RECONCILE_DELAY = timedelta(seconds=settings.deployment_orphan_reconcile_delay_seconds)
# After the deployment token has expired the deploy task can neither report
# steps nor finish the deployment, so it can no longer hold the service lock.
STALE_DEPLOYMENT_AGE = timedelta(minutes=settings.deployment_access_token_expire_minutes)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def last_deployment_activity(deployment: model.Deployment, steps: list[model.Step]) -> datetime | None:
    """
    Latest of the deployment start and the start/finish times of its steps, or
    None if the deployment has no start time.
    """
    started = _as_utc(deployment.started)
    if started is None:
        return None
    timestamps = [started]
    for step in steps:
        for value in (step.started, step.finished):
            as_utc = _as_utc(value)
            if as_utc is not None:
                timestamps.append(as_utc)
    return max(timestamps)


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
    if last_activity is None:
        return True
    return (now - last_activity) < ORPHAN_RECONCILE_DELAY


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


async def get_service_names(fs: AbstractFilesystem) -> list[str]:
    return fs.list()


async def get_services_from_filesystem(fs: AbstractFilesystem) -> list[model.Service]:
    names = await get_service_names(fs)
    services = []
    for name in names:
        services.append(model.Service(name=name, data=fs.get_config_by_name(name)))
    return services


async def get_steps_from_last_deployment(
    service: model.Service, uow: unit_of_work.AbstractUnitOfWork
) -> list[model.Step]:
    steps: list[model.Step] = []
    if service.id is None:
        return steps
    last_successful_deployment_id = await uow.deployments.get_last_successful_deployment_id(service.id)
    if last_successful_deployment_id is not None:
        # try to get steps from last successful deployment
        steps_from_db = await uow.steps.get_steps_by_deployment(last_successful_deployment_id)
        # the orphan marker is not a step of the deploy script
        steps.extend(step for step in steps_from_db if step.name != model.ORPHANED_STEP_NAME)
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
    steps = [model.Step(**step) for step in service.data.get("steps", [])]
    if len(steps) == 0:
        # if no steps are found, create a default placeholder step
        steps.append(model.Step(name="Unknown step"))
    return steps


async def get_all_deployments(uow: unit_of_work.AbstractUnitOfWork) -> list[model.Deployment]:
    """Get a list of all deployments in the database."""
    async with uow:
        deployments = await uow.deployments.list()
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


def deployment_has_open_steps(steps: list[model.Step]) -> bool:
    """Return True if any step indicates the deployment is still active."""
    return any(step.state in OPEN_STEP_STATES for step in steps)


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
    started = _as_utc(deployment.started)
    if started is None:
        return "stale"
    if deployment_is_orphaned(deployment, steps, now):
        return "orphaned"
    if (now - started) >= STALE_DEPLOYMENT_AGE:
        return "stale"
    return "active"


async def get_orphaned_unfinished_deployment_ids(
    uow: unit_of_work.AbstractUnitOfWork,
) -> list[int]:
    """
    Return orphaned unfinished deployments (see ``deployment_is_orphaned``).

    These deployments are reconciled with FinishOrphanedDeployment.
    """
    orphaned_ids: list[int] = []
    now = datetime.now(timezone.utc)
    async with uow:
        deployments = await uow.deployments.list()
        for deployment in deployments:
            if deployment.id is None or deployment.finished is not None:
                continue
            if deployment_is_too_new_for_reconciliation(deployment, now):
                # cheap pre-check, step activity can only make it newer
                continue
            deployment_steps = await uow.steps.get_steps_by_deployment(deployment.id)
            if deployment_is_orphaned(deployment, deployment_steps, now):
                orphaned_ids.append(deployment.id)
    return orphaned_ids


async def is_orphaned_unfinished_deployment(
    deployment_id: int,
    uow: unit_of_work.AbstractUnitOfWork,
) -> bool:
    """
    Return True if the deployment is orphaned (see ``deployment_is_orphaned``).
    """
    deployment = await get_deployment_with_steps(deployment_id, uow)
    return deployment_is_orphaned(deployment, deployment.steps, datetime.now(timezone.utc))


async def all_deployed_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.DeployedService]:
    """Get a list of all deployed services."""
    async with uow:
        deployed = await uow.deployed_services.list()
    return deployed
