from datetime import UTC, datetime

import pytest
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.devices.models import LocationPing
from app.pipeline.utils import Ping
from app.pipeline.writer import write_pings

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class TestWritePings:
    async def test_writes_nothing_for_an_empty_batch(self, db_session: AsyncSession) -> None:
        assert await write_pings(db_session, []) == 0

    async def test_reports_the_number_of_written_pings(self, db_session: AsyncSession) -> None:
        pings = [
            Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT),
            Ping(device_id="dev-2", lat=10.0, lon=20.0, recorded_at=RECORDED_AT),
        ]

        assert await write_pings(db_session, pings) == 2

    async def test_persists_every_ping(self, db_session: AsyncSession) -> None:
        pings = [
            Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT),
            Ping(device_id="dev-2", lat=10.0, lon=20.0, recorded_at=RECORDED_AT),
        ]
        await write_pings(db_session, pings)

        stored = (await db_session.execute(select(LocationPing.device_id).order_by(LocationPing.device_id))).scalars()

        assert list(stored) == ["dev-1", "dev-2"]

    async def test_stores_the_coordinates_as_a_geography_point(self, db_session: AsyncSession) -> None:
        await write_pings(db_session, [Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT)])

        stmt = select(
            func.ST_Y(cast(LocationPing.point, Geometry)),
            func.ST_X(cast(LocationPing.point, Geometry)),
        )
        lat, lon = (await db_session.execute(stmt)).one()

        assert (lat, lon) == pytest.approx((50.45, 30.52))

    async def test_preserves_the_recorded_timestamp(self, db_session: AsyncSession) -> None:
        await write_pings(db_session, [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)])

        stored = (await db_session.execute(select(LocationPing.recorded_at))).scalar_one()

        assert stored == RECORDED_AT
