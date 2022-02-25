from .service_layer import unit_of_work


def service_by_name(name: str, uow: unit_of_work.SqlAlchemyUnitOfWork):
    with uow:
        service = uow.services.get(name)
    return service


def all_services(uow: unit_of_work.AbstractUnitOfWork):
    with uow:
        services_from_db = uow.services.list()
    return services_from_db
