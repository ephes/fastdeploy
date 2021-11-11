from fastapi import APIRouter, Depends

from ..database import repository
from ..dependencies import get_current_active_user
from ..models import Service, User


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_services(current_user: User = Depends(get_current_active_user)) -> list[Service]:
    return await repository.get_services()


@router.post("/")
async def create_service(
    service: Service,
    current_user: User = Depends(get_current_active_user),
) -> Service:
    service.id = None  # prevent client from setting the id
    return await repository.add_service(service)


@router.delete("/{service_id}")
async def delete_service(
    service_id: int,
    current_user: User = Depends(get_current_active_user),
) -> dict:
    await repository.delete_service_by_id(service_id)
    return {"detail": f"Service {service_id} deleted"}
