from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneResponse
from app.domains.geozones.service import GeozoneService
from app.pipeline.matcher import match_zones
from app.pipeline.utils import Ping

pytestmark = pytest.mark.integration

USER = "user-1"
OTHER_USER = "user-2"
CENTER_LAT = 50.45
CENTER_LON = 30.52
RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

INSIDE_LAT = CENTER_LAT + 0.0009
OUTSIDE_LAT = CENTER_LAT + 0.01


def ping(lat: float, lon: float = CENTER_LON, device_id: str = "dev-1", recorded_at: datetime = RECORDED_AT) -> Ping:
    return Ping(device_id=device_id, lat=lat, lon=lon, recorded_at=recorded_at)


class TestMatchZones:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    @pytest.fixture
    async def zone(self, service: GeozoneService) -> GeozoneResponse:
        return await service.create(
            USER, GeozoneCreateRequest(name="home", lat=CENTER_LAT, lon=CENTER_LON, radius_m=500.0)
        )

    async def test_returns_nothing_without_pings(self, db_session: AsyncSession, zone: GeozoneResponse) -> None:
        assert await match_zones(db_session, []) == []

    async def test_matches_a_ping_inside_the_radius(self, db_session: AsyncSession, zone: GeozoneResponse) -> None:
        hits = await match_zones(db_session, [ping(INSIDE_LAT)])

        assert [(hit.geozone_id, hit.geozone_name, hit.user_id, hit.device_id) for hit in hits] == [
            (zone.id, "home", USER, "dev-1")
        ]

    async def test_ignores_a_ping_outside_the_radius(self, db_session: AsyncSession, zone: GeozoneResponse) -> None:
        assert await match_zones(db_session, [ping(OUTSIDE_LAT)]) == []

    async def test_matches_every_device_inside_the_zone(self, db_session: AsyncSession, zone: GeozoneResponse) -> None:
        pings = [ping(INSIDE_LAT, device_id="dev-1"), ping(INSIDE_LAT, device_id="dev-2")]

        hits = await match_zones(db_session, pings)

        assert sorted(hit.device_id for hit in hits) == ["dev-1", "dev-2"]

    async def test_matches_every_zone_covering_the_point(
        self, db_session: AsyncSession, service: GeozoneService, zone: GeozoneResponse
    ) -> None:
        wider = await service.create(
            USER, GeozoneCreateRequest(name="district", lat=CENTER_LAT, lon=CENTER_LON, radius_m=5_000.0)
        )

        hits = await match_zones(db_session, [ping(INSIDE_LAT)])

        assert sorted(hit.geozone_id for hit in hits) == sorted([zone.id, wider.id])

    async def test_matches_zones_of_other_users(
        self, db_session: AsyncSession, service: GeozoneService, zone: GeozoneResponse
    ) -> None:
        foreign = await service.create(
            OTHER_USER, GeozoneCreateRequest(name="home", lat=CENTER_LAT, lon=CENTER_LON, radius_m=500.0)
        )

        hits = await match_zones(db_session, [ping(INSIDE_LAT)])

        assert sorted(hit.geozone_id for hit in hits) == sorted([zone.id, foreign.id])

    async def test_keeps_only_the_latest_ping_per_device_and_zone(
        self, db_session: AsyncSession, zone: GeozoneResponse
    ) -> None:
        pings = [
            ping(INSIDE_LAT, recorded_at=RECORDED_AT),
            ping(INSIDE_LAT, recorded_at=RECORDED_AT + timedelta(minutes=5)),
        ]

        hits = await match_zones(db_session, pings)

        assert [hit.recorded_at for hit in hits] == [RECORDED_AT + timedelta(minutes=5)]
