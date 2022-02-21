from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...bootstrap import get_bus
from ...domain import commands
from ...service_layer.messagebus import MessageBus


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


class Service(BaseModel):
    id: int | None
    name: str
    data: dict


@router.post("/")
async def add_service(service: Service, bus: MessageBus = Depends(get_bus)) -> Service:
    service.id = None  # prevent client from setting the id
    cmd = commands.CreateService(name=service.name, data=service.data)
    bus.handle(cmd)
    with bus.uow:
        stored_service = bus.uow.services.get(service.name)
    return Service(**stored_service.dict())
