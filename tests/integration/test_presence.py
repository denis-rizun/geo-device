from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from app.pipeline.constants import DEVICE_ZONES_KEY
from app.pipeline.presence import filter_new_entries
from app.pipeline.utils import ZoneHit

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
DEVICE = "dev-1"


def hit(geozone_id: int, device_id: str = DEVICE, user_id: str = "user-1") -> ZoneHit:
    return ZoneHit(
        user_id=user_id,
        geozone_id=geozone_id,
        geozone_name=f"zone-{geozone_id}",
        device_id=device_id,
        lat=50.45,
        lon=30.52,
        recorded_at=RECORDED_AT,
    )


class TestFilterNewEntries:
    async def test_returns_nothing_without_devices(self, redis: Redis) -> None:
        assert await filter_new_entries(redis, [hit(1)], []) == []

    async def test_reports_a_first_time_entry(self, redis: Redis) -> None:
        entries = await filter_new_entries(redis, [hit(1)], [DEVICE])

        assert entries == [hit(1)]

    async def test_suppresses_a_device_that_stays_inside(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])

        assert await filter_new_entries(redis, [hit(1)], [DEVICE]) == []

    async def test_reports_a_re_entry_after_leaving(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])
        await filter_new_entries(redis, [], [DEVICE])

        assert await filter_new_entries(redis, [hit(1)], [DEVICE]) == [hit(1)]

    async def test_reports_only_the_newly_entered_zone(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])

        entries = await filter_new_entries(redis, [hit(1), hit(2)], [DEVICE])

        assert entries == [hit(2)]

    async def test_tracks_devices_independently(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])

        entries = await filter_new_entries(redis, [hit(1), hit(1, device_id="dev-2")], [DEVICE, "dev-2"])

        assert entries == [hit(1, device_id="dev-2")]

    async def test_forgets_a_device_that_left_every_zone(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])

        await filter_new_entries(redis, [], [DEVICE])

        assert await redis.exists(DEVICE_ZONES_KEY.format(device_id=DEVICE)) == 0

    async def test_keeps_the_presence_key_alive_while_inside(self, redis: Redis) -> None:
        await filter_new_entries(redis, [hit(1)], [DEVICE])

        assert await redis.ttl(DEVICE_ZONES_KEY.format(device_id=DEVICE)) > 0

    async def test_deduplicates_repeated_device_ids(self, redis: Redis) -> None:
        entries = await filter_new_entries(redis, [hit(1)], [DEVICE, DEVICE])

        assert entries == [hit(1)]
