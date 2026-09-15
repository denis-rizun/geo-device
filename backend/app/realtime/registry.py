import asyncio
from collections import defaultdict

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from structlog.stdlib import BoundLogger

from app.core.config import config

logger = structlog.getLogger(__name__)


class Connection:
    def __init__(self, websocket: WebSocket, user_id: str) -> None:
        self.user_id = user_id
        self._websocket = websocket
        self._message_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=config.realtime.QUEUE_SIZE)
        self._sender: asyncio.Task[None] | None = None
        self._dropped_messages = 0
        self._logger: BoundLogger = logger.bind(user_id=user_id, connection=id(self))

    def start(self) -> None:
        self._sender = asyncio.create_task(self._send_queued(), name=f"ws-sender-{id(self)}")

    async def close(self) -> None:
        if self._sender is None:
            return

        self._sender.cancel()
        await asyncio.gather(self._sender, return_exceptions=True)
        self._sender = None
        if self._dropped_messages:
            self._logger.warning("connection dropped messages", dropped=self._dropped_messages)

    def send(self, message: str, priority: bool = False) -> None:
        if self._message_queue.full():
            if not priority:
                self._dropped_messages += 1
                return

            self._discard_oldest()
        self._message_queue.put_nowait(message)

    def _discard_oldest(self) -> None:
        try:
            self._message_queue.get_nowait()
            self._dropped_messages += 1
        except asyncio.QueueEmpty:
            pass

    async def _send_queued(self) -> None:
        try:
            while True:
                message = await self._message_queue.get()
                await self._websocket.send_text(message)
        except (WebSocketDisconnect, RuntimeError, OSError) as exc:
            self._logger.debug("connection sender stopped", error=str(exc))
            await self._websocket.close()


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connections: dict[str, set[Connection]] = defaultdict(set)

    @property
    def users(self) -> list[str]:
        return list(self._connections)

    def add(self, connection: Connection) -> bool:
        sessions = self._connections[connection.user_id]
        sessions.add(connection)
        return len(sessions) == 1

    def discard(self, connection: Connection) -> bool:
        sessions = self._connections.get(connection.user_id)
        if not sessions:
            return False

        sessions.discard(connection)
        if sessions:
            return False

        del self._connections[connection.user_id]
        return True

    def send_to_user(self, user_id: str, message: str, priority: bool = False) -> None:
        for connection in self._connections.get(user_id, ()):
            connection.send(message, priority)

    def broadcast(self, message: str, priority: bool = False) -> None:
        for sessions in self._connections.values():
            for connection in sessions:
                connection.send(message, priority)
