import asyncio
from collections.abc import MutableMapping
from typing import Any

import pytest
from starlette.websockets import WebSocket

from app.core.config import config
from app.realtime.registry import Connection, ConnectionRegistry

pytestmark = pytest.mark.unit

QUEUE_SIZE = config.realtime.QUEUE_SIZE


class Socket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.websocket = WebSocket({"type": "websocket"}, receive=self._receive, send=self._send)

    async def _receive(self) -> MutableMapping[str, Any]:
        return {"type": "websocket.connect"}

    async def _send(self, message: MutableMapping[str, Any]) -> None:
        if message["type"] == "websocket.send":
            self.sent.append(message["text"])


async def connect(user_id: str = "user-1") -> tuple[Connection, Socket]:
    socket = Socket()
    await socket.websocket.accept()
    return Connection(socket.websocket, user_id), socket


async def drain(connection: Connection, socket: Socket, expected: int) -> list[str]:
    connection.start()
    for _ in range(expected * 2 + 10):
        if len(socket.sent) >= expected:
            break
        await asyncio.sleep(0)

    await connection.close()
    return socket.sent


class TestConnection:
    async def test_queued_messages_reach_the_socket_in_order(self) -> None:
        connection, socket = await connect()

        connection.send("first")
        connection.send("second")

        assert await drain(connection, socket, expected=2) == ["first", "second"]

    async def test_drops_messages_once_the_queue_is_full(self) -> None:
        connection, socket = await connect()

        for index in range(QUEUE_SIZE + 5):
            connection.send(str(index))

        sent = await drain(connection, socket, expected=QUEUE_SIZE)

        assert sent == [str(index) for index in range(QUEUE_SIZE)]

    async def test_priority_messages_evict_the_oldest_when_the_queue_is_full(self) -> None:
        connection, socket = await connect()

        for index in range(QUEUE_SIZE):
            connection.send(str(index))
        connection.send("alert", priority=True)

        sent = await drain(connection, socket, expected=QUEUE_SIZE)

        assert sent == [*(str(index) for index in range(1, QUEUE_SIZE)), "alert"]

    async def test_stops_delivering_after_close(self) -> None:
        connection, socket = await connect()
        connection.start()
        await connection.close()

        connection.send("late")
        await asyncio.sleep(0.05)

        assert socket.sent == []


class TestConnectionRegistry:
    @pytest.fixture
    def registry(self) -> ConnectionRegistry:
        return ConnectionRegistry()

    async def test_reports_the_first_session_of_a_user(self, registry: ConnectionRegistry) -> None:
        connection, _ = await connect("user-1")

        assert registry.add(connection) is True

    async def test_does_not_report_a_second_session_of_the_same_user(self, registry: ConnectionRegistry) -> None:
        first, _ = await connect("user-1")
        second, _ = await connect("user-1")
        registry.add(first)

        assert registry.add(second) is False

    async def test_reports_the_user_leaving_on_the_last_discard(self, registry: ConnectionRegistry) -> None:
        first, _ = await connect("user-1")
        second, _ = await connect("user-1")
        registry.add(first)
        registry.add(second)

        assert [registry.discard(first), registry.discard(second)] == [False, True]

    async def test_discarding_an_unknown_connection_reports_nothing(self, registry: ConnectionRegistry) -> None:
        connection, _ = await connect("user-1")

        assert registry.discard(connection) is False

    async def test_users_lists_only_users_with_open_sessions(self, registry: ConnectionRegistry) -> None:
        first, _ = await connect("user-1")
        second, _ = await connect("user-2")
        registry.add(first)
        registry.add(second)
        registry.discard(first)

        assert registry.users == ["user-2"]

    async def test_send_to_user_reaches_only_that_user(self, registry: ConnectionRegistry) -> None:
        target, target_socket = await connect("user-1")
        other, other_socket = await connect("user-2")
        registry.add(target)
        registry.add(other)

        registry.send_to_user("user-1", "alert")

        assert await drain(target, target_socket, expected=1) == ["alert"]
        assert other_socket.sent == []

    async def test_send_to_an_unknown_user_is_a_no_op(self, registry: ConnectionRegistry) -> None:
        connection, socket = await connect("user-1")
        registry.add(connection)

        registry.send_to_user("user-2", "alert")

        assert socket.sent == []

    async def test_broadcast_reaches_every_user(self, registry: ConnectionRegistry) -> None:
        first, first_socket = await connect("user-1")
        second, second_socket = await connect("user-2")
        registry.add(first)
        registry.add(second)

        registry.broadcast("positions")

        assert await drain(first, first_socket, expected=1) == ["positions"]
        assert await drain(second, second_socket, expected=1) == ["positions"]
