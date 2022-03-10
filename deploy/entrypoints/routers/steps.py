from fastapi import APIRouter, Depends, HTTPException

from ...bootstrap import get_bus
from ...domain import commands
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_deployment
from .helper_models import Deployment, StepResult


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(
    step: StepResult,
    deployment: Deployment = Depends(get_current_active_deployment),
    bus: MessageBus = Depends(get_bus),
) -> dict:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    print("step? ", step)
    cmd = commands.ProcessStep(**step.dict())
    try:
        await bus.handle(cmd)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Something went wrong")
    return {"detail": "step processed"}
