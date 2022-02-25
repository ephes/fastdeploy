from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import views
from ...bootstrap import get_bus
from ...domain import commands, model
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_user


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


class Service(BaseModel):
    id: int | None
    name: str
    data: dict


@router.get("/")
async def get_services(
    _: model.User = Depends(get_current_active_user), bus: MessageBus = Depends(get_bus)
) -> list[Service]:
    """
    Get a list of all services. Need to be authenticated.
    """
    services_from_db = views.all_services(bus.uow)
    return [Service(**s.dict()) for s, in services_from_db]


@router.post("/")
async def add_service(service: Service, bus: MessageBus = Depends(get_bus)) -> Service:
    service.id = None  # prevent client from setting the id
    cmd = commands.CreateService(name=service.name, data=service.data)
    bus.handle(cmd)
    with bus.uow:
        stored_services = bus.uow.services.get(service.name)
        print("stored services: ", stored_services)
    stored_service = stored_services[0]
    print("stored service: ", stored_service)
    # return Service(**stored_service.dict())
    return Service(id=1, name="foobar", data={"foo": "bar"})
