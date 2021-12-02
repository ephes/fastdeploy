from fastapi import APIRouter, Depends, HTTPException

from ..database import repository
from ..dependencies import get_current_active_user
from ..models import Service, User


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_services(_: User = Depends(get_current_active_user)) -> list[Service]:
    return await repository.get_services()


@router.get("/names/")
async def get_service_names(_: User = Depends(get_current_active_user)) -> set[str]:
    return await repository.get_service_names()


@router.post("/")
async def create_service(
    service: Service,
    _: User = Depends(get_current_active_user),
) -> Service:
    service.id = None  # prevent client from setting the id
    service_names = await repository.get_service_names()
    if service.name not in service_names:
        # make sure the service exists
        raise HTTPException(status_code=400, detail="Service does not exists")
    service.data = await repository.get_service_data(service.name)
    return await repository.add_service(service)


@router.delete("/{service_id}")
async def delete_service(
    service_id: int,
    _: User = Depends(get_current_active_user),
) -> dict:
    await repository.delete_service_by_id(service_id)
    return {"detail": f"Service {service_id} deleted"}
