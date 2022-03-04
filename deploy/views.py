from .service_layer import unit_of_work


def service_by_name(name: str, uow: unit_of_work.SqlAlchemyUnitOfWork):
    with uow:
        service = uow.services.get(name)
    return service


async def all_services(uow: unit_of_work.AbstractUnitOfWork):
    async with uow:
        services_from_db = await uow.services.list()
    return services_from_db
