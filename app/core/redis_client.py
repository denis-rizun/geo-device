import asyncio

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import config

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    if not _client:
        raise RuntimeError("Redis client is not initialised")
    return _client


async def init_redis() -> redis.Redis:
    global _client
    _client = redis.from_url(
        config.redis.get_url(),
        decode_responses=False,
        health_check_interval=30,
        socket_keepalive=True,
        socket_timeout=config.redis.SOCKET_TIMEOUT_S,
        socket_connect_timeout=config.redis.CONNECT_TIMEOUT_S,
    )
    await _client.ping()
    return _client


async def check_redis() -> bool:
    if not _client:
        return False

    try:
        async with asyncio.timeout(config.redis.HEALTHCHECK_TIMEOUT_S):
            await _client.ping()
    except RedisError, OSError, TimeoutError:
        return False

    return True


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
