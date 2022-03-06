"""
Readonly views.
"""
from .config import settings
from .filesystem import get_directories
from .service_layer import unit_of_work


async def service_by_name(name: str, uow: unit_of_work.SqlAlchemyUnitOfWork):
    async with uow:
        service = await uow.services.get_by_name(name)
    return service


async def all_services(uow: unit_of_work.AbstractUnitOfWork):
    async with uow:
        services_from_db = await uow.services.list()
    return services_from_db


async def get_service_names() -> list[str]:
    return get_directories(settings.services_root)
