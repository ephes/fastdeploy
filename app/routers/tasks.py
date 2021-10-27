from fastapi import APIRouter, Depends

from ..dependencies import get_current_active_deployment
from ..models import Deployment, Task
from ..websocket import connection_manager


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def tasks(task: Task, deployment: Deployment = Depends(get_current_active_deployment)):
    print("current deployment: ", deployment)
    print("received task: ", task)
    await connection_manager.broadcast(task)
    return {"received": True}
