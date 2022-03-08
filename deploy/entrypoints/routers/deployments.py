from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import views
from ...bootstrap import get_bus
from ...domain import model
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_user


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


class Deployment(BaseModel):
    id: int
    service_id: int
    origin: str
    user: str
    started: datetime | None
    finished: datetime | None
    context: dict


@router.get("/")
async def get_deployments(
    _: model.User = Depends(get_current_active_user), bus: MessageBus = Depends(get_bus)
) -> list[Deployment]:
    """
    Get all deployments from database.
    """
    deployments = await views.get_all_deployments(bus.uow)
    return [Deployment(**d.dict()) for d in deployments]
