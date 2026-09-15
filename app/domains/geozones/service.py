from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import cast, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.utils import GEOGRAPHY_POINT, SRID
from app.domains.geozones.models import Geozone
from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneResponse, GeozoneUpdateRequest

_READ_COLUMNS = (
    Geozone.id,
    Geozone.user_id,
    Geozone.name,
    Geozone.radius_m,
    Geozone.created_at,
    Geozone.updated_at,
    func.ST_Y(cast(Geozone.center, Geometry)).label("lat"),
    func.ST_X(cast(Geozone.center, Geometry)).label("lon"),
)


class GeozoneService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: str, payload: GeozoneCreateRequest) -> GeozoneResponse:
        stmt = (
            insert(Geozone)
            .values(
                user_id=user_id,
                name=payload.name,
                center=self._make_point(payload.lat, payload.lon),
                radius_m=payload.radius_m,
            )
            .returning(*_READ_COLUMNS)
        )
        try:
            row = (await self._session.execute(stmt)).one()
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"Geozone named {payload.name!r} already exists") from exc

        return GeozoneResponse.model_validate(row)

    async def list(self, user_id: str, limit: int = 100, offset: int = 0) -> list[GeozoneResponse]:
        stmt = (
            select(*_READ_COLUMNS)
            .where(Geozone.user_id == user_id)
            .order_by(Geozone.created_at.desc(), Geozone.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).all()
        return [GeozoneResponse.model_validate(row) for row in rows]

    async def retrieve(self, geozone_id: int, user_id: str) -> GeozoneResponse:
        stmt = select(*_READ_COLUMNS).where(Geozone.id == geozone_id, Geozone.user_id == user_id)
        row = (await self._session.execute(stmt)).one_or_none()
        if not row:
            raise NotFoundError(f"Geozone {geozone_id} not found")

        return GeozoneResponse.model_validate(row)

    async def update(self, geozone: GeozoneResponse, payload: GeozoneUpdateRequest) -> GeozoneResponse:
        fields = payload.model_dump(exclude_unset=True)

        updatable_fields = {"name", "radius_m"}
        values = {k: v for k, v in fields.items() if k in updatable_fields}
        if "lat" in fields:
            values["center"] = self._make_point(fields["lat"], fields["lon"])

        stmt = (
            update(Geozone)
            .where(Geozone.id == geozone.id, Geozone.user_id == geozone.user_id)
            .values(**values)
            .returning(*_READ_COLUMNS)
        )
        try:
            row = (await self._session.execute(stmt)).one_or_none()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Geozone name is already taken") from exc

        if not row:
            await self._session.rollback()
            raise NotFoundError(f"Geozone {geozone.id} not found")

        await self._session.commit()
        return GeozoneResponse.model_validate(row)

    async def delete(self, geozone: GeozoneResponse) -> None:
        stmt = delete(Geozone).where(Geozone.id == geozone.id, Geozone.user_id == geozone.user_id).returning(Geozone.id)
        deleted = (await self._session.execute(stmt)).one_or_none()
        if not deleted:
            await self._session.rollback()
            raise NotFoundError(f"Geozone {geozone.id} not found")

        await self._session.commit()

    @staticmethod
    def _make_point(lat: float, lon: float) -> Any:
        return cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID), GEOGRAPHY_POINT)
