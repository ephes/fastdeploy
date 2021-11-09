from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import ServiceToken
from ..database import repository
from ..dependencies import get_current_active_user, get_current_service_token
from ..models import Deployment, User
from ..tasks import get_deploy_environment, run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_deployments(current_user: User = Depends(get_current_active_user)) -> list[Deployment]:
    return repository.get_deployments()


@router.post("/")
async def create_deployment(
    background_tasks: BackgroundTasks, service_token: ServiceToken = Depends(get_current_service_token)
):
    deployment = Deployment(
        service_id=service_token.item_from_db.id, origin=service_token.origin, user=service_token.user
    )
    deployment.created = datetime.now(timezone.utc)  # FIXME: use CURRENT_TIMESTAMP from database
    repository.add_deployment(deployment)
    environment = get_deploy_environment(service_token.item_from_db, deployment)
    background_tasks.add_task(run_deploy, environment)
    return deployment
