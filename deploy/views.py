from .service_layer import unit_of_work


def service_by_name(name: str, uow: unit_of_work.SqlAlchemyUnitOfWork):
    with uow:
        service = uow.services.get(name)
    return service
