from fastapi import APIRouter, Depends

from ..database import repository
from ..dependencies import get_current_active_deployment, get_current_active_user
from ..models import Deployment, Step, StepBase, StepOut, User


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(
    step_in: StepBase, deployment: Deployment = Depends(get_current_active_deployment)
) -> StepOut:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    step = Step(**step_in.dict(), deployment_id=deployment.id)
    step = await deployment.process_step(step)
    return StepOut(**step.dict())


@router.get("/")
async def get_steps_by_deployment(
    deployment_id: int, current_user: User = Depends(get_current_active_user)
) -> list[StepOut]:
    steps = await repository.get_steps_by_deployment_id(deployment_id)
    return [StepOut(**step.dict()) for step in steps]
