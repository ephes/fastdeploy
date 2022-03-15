"""
Readonly views.
"""
from .adapters.filesystem import AbstractFilesystem
from .domain import model
from .service_layer import unit_of_work


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
    return [service for service, in from_db]


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
        steps_from_db = await uow.steps.get_steps_from_deployment(last_successful_deployment_id)
        steps.extend([s for s, in steps_from_db])
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
    return [deployment for deployment, in deployments]


async def get_deployment_with_steps(deployment_id: int, uow: unit_of_work.AbstractUnitOfWork) -> model.Deployment:
    """Get a deployment with all steps."""
    async with uow:
        [deployment] = await uow.deployments.get(deployment_id)
        steps = await uow.steps.get_steps_from_deployment(deployment_id)
        deployment.steps = [s for s, in steps]
    return deployment
