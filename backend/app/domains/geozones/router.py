from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.dependencies import CurrentUserDep
from app.domains.geozones.dependencies import GeozoneDep, GeozoneServiceDep
from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneResponse, GeozoneUpdateRequest

_UNAUTHORIZED = {status.HTTP_401_UNAUTHORIZED: {"description": "X-User-ID header has unsupported format"}}
_NAME_TAKEN = {status.HTTP_409_CONFLICT: {"description": "Geozone with this name already exists"}}
_GEOZONE_ACCESS = {
    status.HTTP_403_FORBIDDEN: {"description": "You don't have an access to that"},
    status.HTTP_404_NOT_FOUND: {"description": "Geozone not found"},
}

router = APIRouter(prefix="/geozones", tags=["Geozones"], responses=_UNAUTHORIZED)


@router.post(
    path="",
    response_model=GeozoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a geozone",
    responses=_NAME_TAKEN,
)
async def create_geozone(
    payload: GeozoneCreateRequest,
    user_id: CurrentUserDep,
    service: GeozoneServiceDep,
) -> GeozoneResponse:
    return await service.create(user_id, payload)


@router.get(
    path="",
    response_model=list[GeozoneResponse],
    summary="List own geozones",
)
async def list_geozones(
    user_id: CurrentUserDep,
    service: GeozoneServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GeozoneResponse]:
    return await service.list(user_id=user_id, limit=limit, offset=offset)


@router.get(
    path="/{id}",
    response_model=GeozoneResponse,
    summary="Retrieve a geozone",
    responses=_GEOZONE_ACCESS,
)
async def get_geozone(geozone: GeozoneDep) -> GeozoneResponse:
    return geozone


@router.patch(
    path="/{id}",
    response_model=GeozoneResponse,
    summary="Update a geozone",
    responses=_GEOZONE_ACCESS | _NAME_TAKEN,
)
async def update_geozone(
    geozone: GeozoneDep,
    payload: GeozoneUpdateRequest,
    service: GeozoneServiceDep,
) -> GeozoneResponse:
    return await service.update(geozone, payload)


@router.delete(
    path="/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a geozone",
    responses=_GEOZONE_ACCESS,
)
async def delete_geozone(geozone: GeozoneDep, service: GeozoneServiceDep) -> Response:
    await service.delete(geozone)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
