from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from app.core.config import config
from app.core.exceptions import ServiceUnavailableError
from app.domains.devices.schemas import LocationBatchRequest, LocationRequest
from app.domains.devices.service import DeviceService
from app.pipeline import stream
from app.pipeline.constants import PENDING_PINGS_KEY, STREAM
from app.pipeline.utils import Ping

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def make_batch(count: int = 2) -> LocationBatchRequest:
    return LocationBatchRequest(
        points=[
            LocationRequest(device_id=f"dev-{index}", lat=50.45, lon=30.52, recorded_at=RECORDED_AT)
            for index in range(count)
        ]
    )


class TestSavePoints:
    @pytest.fixture
    def service(self, redis: Redis) -> DeviceService:
        return DeviceService(redis)

    async def test_accepts_every_point(self, service: DeviceService) -> None:
        accepted = await service.save_points(make_batch(3))

        assert accepted.accepted == 3

    async def test_reports_the_backlog_seen_before_publishing(self, service: DeviceService, redis: Redis) -> None:
        await redis.set(PENDING_PINGS_KEY, 7)

        accepted = await service.save_points(make_batch(1))

        assert accepted.backlog == 7

    async def test_publishes_the_points_to_the_stream(self, service: DeviceService, redis: Redis) -> None:
        await service.save_points(make_batch(2))
        await stream.ensure_group(redis)

        chunks = await stream.read_new(redis, "ingest-0")

        assert [ping for chunk in chunks for ping in chunk.pings] == [
            Ping(device_id="dev-0", lat=50.45, lon=30.52, recorded_at=RECORDED_AT),
            Ping(device_id="dev-1", lat=50.45, lon=30.52, recorded_at=RECORDED_AT),
        ]

    async def test_rejects_a_batch_once_the_backlog_limit_is_exceeded(
        self, service: DeviceService, redis: Redis
    ) -> None:
        await redis.set(PENDING_PINGS_KEY, config.ingest.BACKLOG_LIMIT + 1)

        with pytest.raises(ServiceUnavailableError) as exc_info:
            await service.save_points(make_batch())

        assert exc_info.value.headers == {"Retry-After": "1"}

    async def test_publishes_nothing_when_the_backlog_is_full(self, service: DeviceService, redis: Redis) -> None:
        await redis.set(PENDING_PINGS_KEY, config.ingest.BACKLOG_LIMIT + 1)

        with pytest.raises(ServiceUnavailableError):
            await service.save_points(make_batch())

        assert await redis.exists(STREAM) == 0
