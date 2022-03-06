from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import views
from ...bootstrap import get_bus
from ...domain import commands
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_user


router = APIRouter(
    prefix="/services",
    tags=["services"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


class Service(BaseModel):
    id: int | None
    name: str
    data: dict


@router.get("/")
async def get_services(bus: MessageBus = Depends(get_bus)) -> list[Service]:
    """
    Get a list of all services. Need to be authenticated.
    """
    services_from_db = await views.all_services(bus.uow)
    return [Service(**s.dict()) for s, in services_from_db]


@router.delete("/{service_id}")
async def delete_service(service_id: int, bus: MessageBus = Depends(get_bus)) -> dict:
    """
    Delete a service. Need to be authenticated.
    """
    cmd = commands.DeleteService(service_id=service_id)
    try:
        await bus.handle(cmd)
    except Exception:
        raise HTTPException(status_code=404, detail="Service does not exist")
    return {"detail": f"Service {service_id} deleted"}
