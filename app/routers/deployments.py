from fastapi import APIRouter, BackgroundTasks, Depends

from ..dependencies import get_current_service_token
from ..models import ServiceToken
from ..tasks import run_deploy


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
    # environment = get_deploy_environment(service_token)
    environment = {}
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}
