"""
Readonly views.
"""

from datetime import datetime, timedelta, timezone

from .adapters.filesystem import AbstractFilesystem
from .config import settings
from .domain import model
from .service_layer import unit_of_work

OPEN_STEP_STATES = {"pending", "running"}
ORPHAN_RECONCILE_DELAY = timedelta(seconds=settings.deployment_orphan_reconcile_delay_seconds)


def _normalize_repo_rows(rows):
    """
    Convert repository return values to plain model instances.

    SQL repositories return tuples `(model,)`; in-memory repositories
    often return model instances directly.
    """
    return [_unwrap_repo_row(row) for row in rows]


def _unwrap_repo_row(row):
    """
    Extract a mapped model from repository return values.

    SQLAlchemy 2 may return `Row` wrappers for `result.one()` / `result.all()`
    instead of plain tuples, even when the select only contains a single model.
    """
    if hasattr(row, "_mapping"):
        values = tuple(row._mapping.values())
        if len(values) == 1:
            return values[0]
    if isinstance(row, tuple):
        return row[0]
    return row


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def deployment_is_too_new_for_reconciliation(
    deployment: model.Deployment,
    now: datetime,
) -> bool:
    """
    Avoid reconciling brand-new deployments during the startup race window.
    """
    started = _as_utc(deployment.started)
    if started is None:
        return True
    return (now - started) < ORPHAN_RECONCILE_DELAY


async def get_user_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork) -> model.User:
    async with uow:
        user = _unwrap_repo_row(await uow.users.get(name))
    return user


async def service_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork):
    async with uow:
        service = _unwrap_repo_row(await uow.services.get_by_name(name))
    return service


async def all_synced_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.Service]:
    async with uow:
        from_db = await uow.services.list()
    return _normalize_repo_rows(from_db)


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
        steps.extend(_normalize_repo_rows(steps_from_db))
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
    return _normalize_repo_rows(deployments)


async def get_deployment_with_steps(deployment_id: int, uow: unit_of_work.AbstractUnitOfWork) -> model.Deployment:
    """Get a deployment with all steps."""
    async with uow:
        deployment = _unwrap_repo_row(await uow.deployments.get(deployment_id))
        steps = await uow.steps.get_steps_by_deployment(deployment_id)
        deployment.steps = _normalize_repo_rows(steps)
    return deployment


def deployment_has_open_steps(steps: list[model.Step]) -> bool:
    """Return True if any step indicates the deployment is still active."""
    return any(step.state in OPEN_STEP_STATES for step in steps)


async def get_orphaned_unfinished_deployment_ids(
    uow: unit_of_work.AbstractUnitOfWork,
) -> list[int]:
    """
    Return unfinished deployments that have no running/pending steps.

    These deployments are safe to reconcile by calling FinishDeployment.
    """
    orphaned_ids: list[int] = []
    now = datetime.now(timezone.utc)
    async with uow:
        deployments = _normalize_repo_rows(await uow.deployments.list())
        for deployment in deployments:
            if deployment.id is None or deployment.finished is not None:
                continue
            if deployment_is_too_new_for_reconciliation(deployment, now):
                continue
            steps = await uow.steps.get_steps_by_deployment(deployment.id)
            deployment_steps = _normalize_repo_rows(steps)
            if not deployment_has_open_steps(deployment_steps):
                orphaned_ids.append(deployment.id)
    return orphaned_ids


async def is_orphaned_unfinished_deployment(
    deployment_id: int,
    uow: unit_of_work.AbstractUnitOfWork,
) -> bool:
    """
    Return True if deployment is unfinished and has no running/pending steps.
    """
    deployment = await get_deployment_with_steps(deployment_id, uow)
    if deployment.finished is not None:
        return False
    if deployment_is_too_new_for_reconciliation(deployment, datetime.now(timezone.utc)):
        return False
    return not deployment_has_open_steps(deployment.steps)


async def all_deployed_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.DeployedService]:
    """Get a list of all deployed services."""
    async with uow:
        deployed = await uow.deployed_services.list()
    return _normalize_repo_rows(deployed)
