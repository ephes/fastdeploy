from fastapi import APIRouter, Depends

from ..auth import CREDENTIALS_EXCEPTION
from ..database import repository
from ..dependencies import get_current_active_user, get_current_deployment
from ..models import Deployment, Step, StepBase, StepOut, User


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def create_step(step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)) -> StepOut:
    print("step in: ", step_in)
    step = Step(**step_in.dict(), deployment_id=deployment.id)
    print("create step: ", step)
    step = await repository.add_step(step)
    return StepOut.parse_obj(step)


@router.get("/")
async def get_steps_by_deployment(
    deployment_id: int, current_user: User = Depends(get_current_active_user)
) -> list[StepOut]:
    steps = await repository.get_steps_by_deployment_id(deployment_id)
    return [StepOut.parse_obj(step) for step in steps]


@router.put("/{step_id}")
async def step_update(
    step_id: int, step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)
) -> StepOut:
    step = repository.get_step_by_id(step_id)
    if step.deployment_id != deployment.id:
        raise CREDENTIALS_EXCEPTION
    step.name = step_in.name
    step.started = step_in.started
    step.finished = step_in.finished
    step = await repository.update_step(step)
    return StepOut.parse_obj(step)
