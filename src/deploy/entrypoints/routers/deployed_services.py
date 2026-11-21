from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ... import views
from ..dependencies import get_current_config
from ..helper_models import POSTGRES_INTEGER_MAX, Bus

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
async def list_deployed_services(
    bus: Bus = Depends(),
    limit: int | None = Query(None, ge=1, le=200),
    before_id: int | None = Query(None, ge=1, le=POSTGRES_INTEGER_MAX),
) -> list[DeployedService]:
    """List deployed services by descending ID, with optional cursor pagination."""
    if before_id is not None and limit is None:
        limit = 50
    deployed_services_from_db = await views.all_deployed_services(bus.uow, limit=limit, before_id=before_id)
    return [DeployedService(**d.model_dump()) for d in deployed_services_from_db]
