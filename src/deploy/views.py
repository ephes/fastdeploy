"""
Readonly views.
"""

from .adapters.filesystem import AbstractFilesystem
from .domain import model
from .service_layer import unit_of_work

OPEN_STEP_STATES = {"pending", "running"}


def _normalize_repo_rows(rows):
    """
    Convert repository return values to plain model instances.

    SQL repositories return tuples `(model,)`; in-memory repositories
    often return model instances directly.
    """
    models = []
    for row in rows:
        if isinstance(row, tuple):
            models.append(row[0])
        else:
            models.append(row)
    return models


async def get_user_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork) -> model.User:
    async with uow:
        [user] = await uow.users.get(name)
    return user


async def service_by_name(name: str, uow: unit_of_work.AbstractUnitOfWork):
    async with uow:
        service = await uow.services.get_by_name(name)
    return service


async def all_synced_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.Service]:
    async with uow:
        from_db = await uow.services.list()
    return [service for (service,) in from_db]


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
        steps.extend([s for (s,) in steps_from_db])
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
        [deployment] = await uow.deployments.get(deployment_id)
        steps = await uow.steps.get_steps_by_deployment(deployment_id)
        deployment.steps = [s for (s,) in steps]
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
    async with uow:
        deployments = _normalize_repo_rows(await uow.deployments.list())
        for deployment in deployments:
            if deployment.id is None or deployment.finished is not None:
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
    return not deployment_has_open_steps(deployment.steps)


async def all_deployed_services(uow: unit_of_work.AbstractUnitOfWork) -> list[model.DeployedService]:
    """Get a list of all deployed services."""
    async with uow:
        deployed = await uow.deployed_services.list()
    return [dservice for (dservice,) in deployed]
