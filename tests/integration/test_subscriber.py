import asyncio
from collections.abc import AsyncGenerator, MutableMapping
from datetime import UTC, datetime
from typing import Any

import orjson
import pytest
from redis.asyncio import Redis
from starlette.websockets import WebSocket

from app.pipeline.utils import Ping, ZoneHit
from app.realtime.constants import ALERT_MESSAGE_TYPE, POSITION_MESSAGE_TYPE
from app.realtime.events import publish_alerts, publish_positions
from app.realtime.registry import Connection
from app.realtime.subscriber import Subscriber

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
DELIVERY_TIMEOUT_S = 2.0


class Socket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.websocket = WebSocket({"type": "websocket"}, receive=self._receive, send=self._send)

    async def _receive(self) -> MutableMapping[str, Any]:
        return {"type": "websocket.connect"}

    async def _send(self, message: MutableMapping[str, Any]) -> None:
        if message["type"] == "websocket.send":
            self.sent.append(message["text"])

    async def wait(self) -> dict[str, Any]:
        async with asyncio.timeout(DELIVERY_TIMEOUT_S):
            while not self.sent:
                await asyncio.sleep(0.01)
        return orjson.loads(self.sent[0])  # type: ignore[no-any-return]


async def attach(subscriber: Subscriber, user_id: str) -> tuple[Connection, Socket]:
    socket = Socket()
    await socket.websocket.accept()
    connection = Connection(socket.websocket, user_id)
    await subscriber.attach(connection)
    await asyncio.sleep(0.05)
    return connection, socket


async def socket_settled(socket: Socket) -> None:
    await socket.wait()
    await asyncio.sleep(0.1)


def hit(user_id: str) -> ZoneHit:
    return ZoneHit(
        user_id=user_id,
        geozone_id=1,
        geozone_name="home",
        device_id="dev-1",
        lat=50.45,
        lon=30.52,
        recorded_at=RECORDED_AT,
    )


class TestSubscriber:
    @pytest.fixture
    async def subscriber(self, redis: Redis) -> AsyncGenerator[Subscriber]:
        subscriber = Subscriber(redis)
        await subscriber.start()
        yield subscriber
        await subscriber.stop()

    async def test_delivers_an_alert_to_the_owning_user(self, subscriber: Subscriber, redis: Redis) -> None:
        _, socket = await attach(subscriber, "user-1")

        await publish_alerts(redis, [hit("user-1")])

        assert (await socket.wait())["type"] == ALERT_MESSAGE_TYPE

    async def test_keeps_an_alert_away_from_other_users(self, subscriber: Subscriber, redis: Redis) -> None:
        _, listener = await attach(subscriber, "user-1")
        _, outsider = await attach(subscriber, "user-2")

        await publish_alerts(redis, [hit("user-1")])
        await socket_settled(listener)

        assert outsider.sent == []

    async def test_broadcasts_positions_to_every_user(self, subscriber: Subscriber, redis: Redis) -> None:
        _, first = await attach(subscriber, "user-1")
        _, second = await attach(subscriber, "user-2")

        await publish_positions(redis, [Ping(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=RECORDED_AT)])

        assert (await first.wait())["type"] == POSITION_MESSAGE_TYPE
        assert (await second.wait())["type"] == POSITION_MESSAGE_TYPE

    async def test_stops_delivering_after_detach(self, subscriber: Subscriber, redis: Redis) -> None:
        connection, socket = await attach(subscriber, "user-1")
        await subscriber.detach(connection)
        await asyncio.sleep(0.05)

        await publish_alerts(redis, [hit("user-1")])
        await asyncio.sleep(0.2)

        assert socket.sent == []
