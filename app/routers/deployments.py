from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import ServiceToken
from ..database import repository
from ..dependencies import (
    get_current_active_deployment,
    get_current_active_service_token,
    get_current_active_user,
)
from ..models import Deployment, DeploymentOut, User
from ..tasks import get_deploy_environment, run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_deployments(_: User = Depends(get_current_active_user)) -> list[Deployment]:
    """
    Get all deployments from database. Needs to be authenticated with a user
    access token.
    """
    return await repository.get_deployments()


@router.post("/")
async def start_deployment(
    background_tasks: BackgroundTasks, service_token: ServiceToken = Depends(get_current_active_service_token)
) -> DeploymentOut:
    """
    Start a new deployment. Needs to be authenticated with a service token. Invoked
    by frontend or github action. The service token is used to get the current
    service from the database. The list of steps is fetched from service and added
    to the deployment. The deployment is started a background task (forking a new
    process later on).
    """
    service = service_token.service_model
    assert service is not None
    service_id = service.id
    assert service_id is not None

    deployment = Deployment(service_id=service_id, origin=service_token.origin, user=service_token.user)
    deployment.created = datetime.now(timezone.utc)  # FIXME: use CURRENT_TIMESTAMP from database
    deployment, steps = await repository.add_deployment(deployment, service.get_steps())
    environment = get_deploy_environment(deployment, steps, service.get_deploy_script())
    background_tasks.add_task(run_deploy, environment)
    return DeploymentOut(**deployment.dict())


@router.put("/finish/")
async def finish_deployment(deployment: Deployment = Depends(get_current_active_deployment)) -> DeploymentOut:
    """
    Finish a deployment. Need to be authenticated with a deployment access token.
    We set the finished timestamp on the server side because it should not be
    possible to update any deployment attributes.
    """
    deployment.finished = datetime.now(timezone.utc)
    deployment = await repository.update_deployment(deployment)
    return DeploymentOut(**deployment.dict())
