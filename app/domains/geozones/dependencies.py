from typing import Annotated

from fastapi import Depends, Path

from app.dependencies import CurrentUserDep, SessionDep
from app.domains.geozones.schemas import GeozoneResponse
from app.domains.geozones.service import GeozoneService


def get_geozone_service(session: SessionDep) -> GeozoneService:
    return GeozoneService(session)


GeozoneServiceDep = Annotated[GeozoneService, Depends(get_geozone_service)]


async def get_geozone(
    id: Annotated[int, Path(ge=1)],
    service: GeozoneServiceDep,
    user_id: CurrentUserDep,
) -> GeozoneResponse:
    return await service.retrieve(id, user_id)


GeozoneDep = Annotated[GeozoneResponse, Depends(get_geozone)]
