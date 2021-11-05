from fastapi import APIRouter, Depends

from ..database import repository
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


@router.post("/")
async def create_service(
    service: Service,
    current_user: User = Depends(get_current_active_user),
) -> Service:
    print("service in: ", service)
    return repository.add_service(service)
