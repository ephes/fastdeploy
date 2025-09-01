from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import views
from ...domain import commands
from ..dependencies import get_current_active_user
from ..helper_models import Bus

router = APIRouter(
    prefix="/services",
    tags=["services"],
    # all requests to endpoints in this router need to be authenticated
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


class Service(BaseModel):
    id: int | None
    name: str
    data: dict


@router.get("/")
async def get_services(bus: Bus = Depends()) -> list[Service]:
    """
    Get a list of all services.
    """
    services_from_db = await views.all_synced_services(bus.uow)
    return [Service(**s.model_dump()) for s in services_from_db]


@router.delete("/{service_id}")
async def delete_service(service_id: int, bus: Bus = Depends()) -> dict:
    """
    Delete a service.
    """
    cmd = commands.DeleteService(service_id=service_id)
    try:
        await bus.handle(cmd)
    except Exception:
        raise HTTPException(status_code=404, detail="Service does not exist")
    return {"detail": f"Service {service_id} deleted"}


@router.get("/names/")
async def get_service_names(bus: Bus = Depends()) -> list[str]:
    """
    Get a list of all available service names Only available services can be created.
    """
    return await views.get_service_names(bus.fs)


@router.post("/sync")
async def sync_services(bus: Bus = Depends()) -> dict:
    """
    Sync services from filesytem to database.
    """
    cmd = commands.SyncServices()
    await bus.handle(cmd)
    return {"detail": "Services synced"}
