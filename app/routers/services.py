from fastapi import APIRouter, Depends

from ..dependencies import get_current_active_user
from ..models import Service, User, get_services_from_db


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_services(current_user: User = Depends(get_current_active_user)) -> list[Service]:
    services = get_services_from_db()
    return services
