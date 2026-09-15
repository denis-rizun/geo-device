import asyncio
from datetime import UTC, datetime
from typing import Any

import orjson
import pytest
from redis.asyncio import Redis

from app.pipeline.utils import Ping, ZoneHit
from app.realtime.constants import ALERT_CHANNEL, ALERT_MESSAGE_TYPE, POSITION_CHANNEL, POSITION_MESSAGE_TYPE
from app.realtime.events import publish_alerts, publish_positions

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
LISTEN_TIMEOUT_S = 2.0


def hit(user_id: str = "user-1", geozone_id: int = 1) -> ZoneHit:
    return ZoneHit(
        user_id=user_id,
        geozone_id=geozone_id,
        geozone_name=f"zone-{geozone_id}",
        device_id="dev-1",
        lat=50.45,
        lon=30.52,
        recorded_at=RECORDED_AT,
    )


async def listen(redis: Redis, channel: str) -> dict[str, Any]:
    pubsub = redis.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(channel)
    try:
        async with asyncio.timeout(LISTEN_TIMEOUT_S):
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
                if message:
                    return orjson.loads(message["data"])
    finally:
        await pubsub.aclose()


class TestPublishAlerts:
    async def test_publishes_nothing_for_an_empty_list(self, redis: Redis) -> None:
        assert await publish_alerts(redis, []) == 0

    async def test_reports_the_number_of_published_alerts(self, redis: Redis) -> None:
        assert await publish_alerts(redis, [hit(), hit(geozone_id=2)]) == 2

    async def test_delivers_the_alert_to_the_owning_user(self, redis: Redis) -> None:
        listener = asyncio.create_task(listen(redis, ALERT_CHANNEL.format(user_id="user-1")))
        await asyncio.sleep(0.05)

        await publish_alerts(redis, [hit()])
        payload = await listener

        assert payload["type"] == ALERT_MESSAGE_TYPE

    async def test_sends_only_the_alerts_of_that_user(self, redis: Redis) -> None:
        listener = asyncio.create_task(listen(redis, ALERT_CHANNEL.format(user_id="user-1")))
        await asyncio.sleep(0.05)

        await publish_alerts(redis, [hit(user_id="user-1"), hit(user_id="user-2", geozone_id=2)])
        payload = await listener

        assert [alert["user_id"] for alert in payload["alerts"]] == ["user-1"]


class TestPublishPositions:
    async def test_publishes_nothing_for_an_empty_list(self, redis: Redis) -> None:
        assert await publish_positions(redis, []) == 0

    async def test_reports_the_number_of_published_positions(self, redis: Redis) -> None:
        positions = [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)]

        assert await publish_positions(redis, positions) == 1

    async def test_broadcasts_the_positions(self, redis: Redis) -> None:
        listener = asyncio.create_task(listen(redis, POSITION_CHANNEL))
        await asyncio.sleep(0.05)

        await publish_positions(redis, [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)])
        payload = await listener

        assert payload == {
            "type": POSITION_MESSAGE_TYPE,
            "positions": [["dev-1", 1.0, 2.0, RECORDED_AT.isoformat()]],
        }
