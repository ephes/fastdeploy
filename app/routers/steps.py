from fastapi import APIRouter, Depends

from ..dependencies import get_current_active_deployment
from ..models import Deployment, Step
from ..websocket import connection_manager


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def steps(step: Step, deployment: Deployment = Depends(get_current_active_deployment)):
    print("current deployment: ", deployment)
    print("received step: ", step)
    await connection_manager.broadcast(step)
    return {"received": True}
