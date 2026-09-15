import redis.asyncio as redis

from app.core.config import config

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis client is not initialised")
    return _client


async def init_redis() -> redis.Redis:
    global _client
    _client = redis.from_url(
        config.redis.get_url(),
        decode_responses=False,
        health_check_interval=30,
        socket_keepalive=True,
    )
    await _client.ping()
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
