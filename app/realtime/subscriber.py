import asyncio

import structlog
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

from app.pipeline.utils import Backoff
from app.realtime.constants import (
    ALERT_CHANNEL,
    ALERT_CHANNEL_PREFIX,
    POSITION_CHANNEL,
    RESUBSCRIBE_BACKOFF_MAX_S,
    RESUBSCRIBE_BACKOFF_S,
)
from app.realtime.registry import Connection, ConnectionRegistry

logger = structlog.getLogger(__name__)

_subscriber: Subscriber | None = None


class Subscriber:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._registry = ConnectionRegistry()
        self._pubsub: PubSub = redis.pubsub(ignore_subscribe_messages=True)
        self._backoff = Backoff(RESUBSCRIBE_BACKOFF_S, RESUBSCRIBE_BACKOFF_MAX_S)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._pubsub.subscribe(POSITION_CHANNEL)
        self._task = asyncio.create_task(self._run(), name="realtime-subscriber")
        logger.info("realtime subscriber started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

        await self._pubsub.aclose()
        logger.info("realtime subscriber stopped")

    async def attach(self, connection: Connection) -> None:
        connection.start()
        if self._registry.add(connection):
            await self._pubsub.subscribe(ALERT_CHANNEL.format(user_id=connection.user_id))

    async def detach(self, connection: Connection) -> None:
        if self._registry.discard(connection):
            await self._pubsub.unsubscribe(ALERT_CHANNEL.format(user_id=connection.user_id))

        await connection.close()

    async def _run(self) -> None:
        while True:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
                self._backoff.reset()
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError) as exc:
                logger.warning("subscriber read failed", error=str(exc))
                await self._backoff.sleep()
                await self._resubscribe()
                continue

            if message:
                self._dispatch(message)

    async def _resubscribe(self) -> None:
        channels = [POSITION_CHANNEL, *(ALERT_CHANNEL.format(user_id=user) for user in self._registry.users)]
        try:
            await self._pubsub.subscribe(*channels)
            logger.info("subscriber resubscribed", channels_count=len(channels))
        except (RedisError, OSError) as exc:
            logger.warning("resubscribe failed", error=str(exc))

    def _dispatch(self, message: dict[str, bytes]) -> None:
        channel = message["channel"].decode()
        payload = message["data"].decode()
        if channel == POSITION_CHANNEL:
            self._registry.broadcast(payload)
            return

        self._registry.send_to_user(channel.removeprefix(ALERT_CHANNEL_PREFIX), payload, priority=True)


def get_subscriber() -> Subscriber:
    if not _subscriber:
        raise RuntimeError("Realtime subscriber is not initialised")
    return _subscriber


async def init_subscriber(redis: Redis) -> Subscriber:
    global _subscriber
    _subscriber = Subscriber(redis)
    await _subscriber.start()
    return _subscriber


async def close_subscriber() -> None:
    global _subscriber
    if _subscriber:
        await _subscriber.stop()
        _subscriber = None
