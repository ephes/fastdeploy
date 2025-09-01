from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import views
from ..dependencies import get_current_config
from ..helper_models import Bus

router = APIRouter(
    prefix="/deployed-services",
    tags=["deployed-services"],
    # all requests to endpoints in this router need to be authenticated
    # with a valid config token
    dependencies=[Depends(get_current_config)],
    responses={404: {"description": "Not found"}},
)


class DeployedService(BaseModel):
    id: int
    deployment_id: int
    config: dict


@router.get("/")
async def list_deployed_services(bus: Bus = Depends()) -> list[DeployedService]:
    """
    Get a list of all deployed services.
    """
    deployed_services_from_db = await views.all_deployed_services(bus.uow)
    return [DeployedService(**d.model_dump()) for d in deployed_services_from_db]
