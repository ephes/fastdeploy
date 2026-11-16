import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from jwt import InvalidTokenError

from ... import views
from ...auth import InvalidCredentials
from ...domain import commands, model
from ..dependencies import CREDENTIALS_EXCEPTION, OAUTH2_SCHEME, get_current_active_deployment, get_current_active_user
from ..helper_models import Bus, Deployment, Step, StepResult

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", responses={409: {"description": "The step was already reported with a different result"}})
async def process_step_result(
    step: StepResult,
    token: str = Depends(OAUTH2_SCHEME),
    deployment: Deployment = Depends(get_current_active_deployment),
    bus: Bus = Depends(),
) -> dict:
    """
    The deployment process reports a step here: with the state running when it
    starts (optional) and with its result (success or failure) when it is finished.
    Needs to be authenticated with a deployment token.

    Reporting is idempotent: sending the same result again (same name, started
    timestamp, state and message) changes nothing and is answered like the first
    report. The same name and started timestamp with a different state or message
    is rejected with 409 Conflict.
    """
    assert isinstance(deployment.id, int)
    cmd = commands.ProcessStep(**step.model_dump(), deployment_id=deployment.id, deployment_token=token)
    try:
        await bus.handle(cmd)
    except (InvalidCredentials, InvalidTokenError):
        raise CREDENTIALS_EXCEPTION from None
    except model.StepReportConflict as e:
        logger.warning("conflicting repeated step report for deployment %s", deployment.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Step was already reported with a different result"
        ) from e
    except Exception as e:
        logger.warning("could not process step for deployment %s", deployment.id, exc_info=True)
        raise HTTPException(status_code=400, detail="Something went wrong") from e
    return {"detail": "step processed"}


@router.get("/", dependencies=[Depends(get_current_active_user)])
async def get_steps_by_deployment(
    deployment_id: int,
    bus: Bus = Depends(),
    limit: int = Query(25, ge=1, le=25),
    before_id: int | None = Query(None, ge=1),
) -> list[Step]:
    """
    Get a bounded step page, newest id first. A short page completes the inventory.
    """
    try:
        steps = await views.get_step_page(deployment_id, bus.uow, limit=limit, before_id=before_id)
    except views.DeploymentNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found") from e

    return [Step(**step.model_dump()) for step in steps]
