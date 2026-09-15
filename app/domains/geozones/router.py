from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.dependencies import CurrentUserDep
from app.domains.geozones.dependencies import GeozoneDep, GeozoneServiceDep
from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneResponse, GeozoneUpdateRequest

router = APIRouter(
    prefix="/geozones",
    tags=["Geozones"],
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "X-User-ID header has unsupported format"}},
)


@router.post(
    path="",
    response_model=GeozoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a geozone",
    responses={status.HTTP_409_CONFLICT: {"description": "Geozone with this name already exists"}},
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
    return await service.list(user_id, limit=limit, offset=offset)


@router.get(
    path="/{id}",
    response_model=GeozoneResponse,
    summary="Retrieve a geozone",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Geozone not found"}},
)
async def get_geozone(geozone: GeozoneDep) -> GeozoneResponse:
    return geozone


@router.patch(
    path="/{id}",
    response_model=GeozoneResponse,
    summary="Update a geozone",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Geozone not found"},
        status.HTTP_409_CONFLICT: {"description": "Geozone with this name already exists"},
    },
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
    responses={status.HTTP_404_NOT_FOUND: {"description": "Geozone not found"}},
)
async def delete_geozone(geozone: GeozoneDep, service: GeozoneServiceDep) -> Response:
    await service.delete(geozone)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
