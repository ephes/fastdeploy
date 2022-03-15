from fastapi import APIRouter, Depends, HTTPException

from ... import views
from ...domain import commands
from ..dependencies import get_current_active_deployment, get_current_active_user
from ..helper_models import Bus, Deployment, Step, StepResult


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(
    step: StepResult,
    deployment: Deployment = Depends(get_current_active_deployment),
    bus: Bus = Depends(),
) -> dict:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    cmd = commands.ProcessStep(**step.dict(), deployment_id=deployment.id)
    try:
        await bus.handle(cmd)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Something went wrong")
    return {"detail": "step processed"}


@router.get("/", dependencies=[Depends(get_current_active_user)])
async def get_steps_by_deployment(
    deployment_id: int,
    bus: Bus = Depends(),
) -> list[Step]:
    """
    Get all steps for a deployment.
    """
    async with bus.uow as uow:
        deployment = await views.get_deployment_with_steps(deployment_id, uow)

    return [Step(**step.dict()) for step in deployment.steps]
