from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import ServiceToken
from ..dependencies import get_current_service_token
from ..models import Deployment, add_deployment
from ..tasks import get_deploy_environment, run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_root():
    return {"Hello": "Deployments"}


@router.post("/")
async def deployments(
    background_tasks: BackgroundTasks, service_token: ServiceToken = Depends(get_current_service_token)
):
    print("received deploy event for service and origin: ", service_token)
    deployment = Deployment(
        service_id=service_token.item_from_db.id, origin=service_token.origin, user=service_token.user
    )
    add_deployment(deployment)
    environment = get_deploy_environment(deployment)
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}
