from fastapi import APIRouter, Depends

from ..dependencies import get_current_deployment
from ..models import Deployment, Step, StepBase
from ..websocket import connection_manager


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def steps(step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)):
    print("current deployment: ", deployment)
    print("received step_in: ", step_in)
    step = Step(**step_in.dict(), deployment_id=deployment.id)
    print("received step: ", step)
    await connection_manager.broadcast(step)
    return {"received": True}
