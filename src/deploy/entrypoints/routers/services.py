from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound

from ... import views
from ...adapters.filesystem import ServiceConfigError
from ...domain import commands, model
from ..dependencies import get_current_active_user
from ..helper_models import POSTGRES_INTEGER_MAX, Bus

router = APIRouter(
    prefix="/services",
    tags=["services"],
    # all requests to endpoints in this router need to be authenticated
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


class Service(BaseModel):
    id: int | None
    name: str
    data: dict


@router.get("/")
async def get_services(bus: Bus = Depends()) -> list[Service]:
    """
    Get a list of all services.
    """
    services_from_db = await views.all_synced_services(bus.uow)
    return [Service(**s.model_dump()) for s in services_from_db]


@router.delete(
    "/{service_id}",
    responses={409: {"description": "The service has a running deployment and was not deleted"}},
)
async def delete_service(service_id: int, bus: Bus = Depends()) -> dict:
    """
    Delete a service together with its deployments and steps.

    A service with a running deployment is not deleted: the request is
    rejected with 409 Conflict and nothing changes.
    """
    if not 1 <= service_id <= POSTGRES_INTEGER_MAX:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service does not exist")

    cmd = commands.DeleteService(service_id=service_id)
    try:
        await bus.handle(cmd)
    except model.ServiceHasActiveDeployment as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(e), "deployment_id": e.deployment_id},
        ) from e
    except NoResultFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service does not exist") from e
    return {"detail": f"Service {service_id} deleted"}


@router.get("/names/", responses={422: {"description": "The services directory was refused by source admission"}})
async def get_service_names(bus: Bus = Depends()) -> list[str]:
    """
    Get a list of all available service names Only available services can be created.

    A services directory that cannot be listed or exceeds the source admission
    limits is refused with 422, like a sync of the same directory.
    """
    try:
        return await views.get_service_names(bus.fs)
    except ServiceConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class SkippedService(BaseModel):
    name: str
    reason: str


class SyncResult(BaseModel):
    detail: str
    updated: list[str]
    deleted: list[str]
    skipped: list[SkippedService]


@router.post(
    "/sync",
    responses={409: {"description": "Sync needs confirmation of the current deletion candidates"}},
)
async def sync_services(
    force: bool = Query(False, description="Delete services even if all or more than half of them would be removed"),
    confirmation: str | None = Query(
        None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="Deletion confirmation from HTTP 409",
    ),
    bus: Bus = Depends(),
) -> SyncResult:
    """
    Sync services from filesytem to database.

    Services without a directory are deleted together with their deployments.
    A sync that would delete all services or more than half of them is refused
    with 409 Conflict unless `force=true` is passed. Services with a running
    deployment are never deleted and are reported as skipped. If a deletion
    confirmation is supplied, it must still match the planned deletions.
    """
    cmd = commands.SyncServices(force=force, confirmation=confirmation)
    try:
        result: model.ServiceSyncResult = await bus.handle(cmd)
    except ServiceConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except model.ServiceSyncRefused as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": e.reason,
                "would_delete": e.would_delete,
                "total": e.total,
                "confirmation": e.confirmation,
            },
        ) from e
    return SyncResult(
        detail="Services synced",
        updated=result.updated,
        deleted=result.deleted,
        skipped=[SkippedService(name=s.name, reason=s.reason) for s in result.skipped],
    )
