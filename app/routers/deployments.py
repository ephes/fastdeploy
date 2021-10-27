from fastapi import APIRouter, BackgroundTasks, Depends

from ..dependencies import get_current_service_and_origin
from ..models import ServiceAndOrigin
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
    background_tasks: BackgroundTasks, service_and_origin: ServiceAndOrigin = Depends(get_current_service_and_origin)
):
    print("received deploy event for service and origin: ", service_and_origin)
    environment = get_deploy_environment(service_and_origin)
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}
