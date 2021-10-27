from fastapi import APIRouter, Depends

from ..dependencies import (
    get_current_active_user,
    get_current_service,
    get_service_by_name,
)
from ..models import Service, User
from ..websocket import connection_manager


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description": "Not found"}},
)


@router.post("/by-user")
async def task_by_user(taskresult: dict, current_user: User = Depends(get_current_active_user)):
    print("received taskresult: ", taskresult)
    await connection_manager.broadcast(taskresult)
    return {"received": True}


@router.post("/by-service")
async def task_by_service(taskresult: dict, current_service: Service = Depends(get_current_service)):
    print("received taskresult: ", taskresult)
    get_service_by_name(current_service.name)
    await connection_manager.broadcast(taskresult)
    return {"received": True}
