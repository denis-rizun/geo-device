from itertools import batched

import structlog
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.config import config
from app.pipeline.constants import (
    BLOCK_MS,
    CLAIM_IDLE_MS,
    GROUP,
    GROUP_EXISTS_PREFIX,
    NEW_MESSAGES,
    PAYLOAD_FIELD,
    PENDING_PINGS_KEY,
    READ_COUNT,
    STREAM,
)
from app.pipeline.utils import Ping, StreamChunk, encode_pings, parse_stream_chunk

logger = structlog.getLogger(__name__)


async def publish(redis: Redis, pings: list[Ping]) -> None:
    if not pings:
        return

    async with redis.pipeline(transaction=False) as pipe:
        for chunk in batched(pings, config.ingest.CHUNK_SIZE, strict=False):
            await pipe.xadd(
                name=STREAM,
                fields={PAYLOAD_FIELD: encode_pings(list(chunk))},
                maxlen=config.ingest.STREAM_MAX_LEN,
                approximate=True,
            )
        await pipe.incrby(PENDING_PINGS_KEY, len(pings))
        await pipe.execute()


async def get_backlog(redis: Redis) -> int:
    pending = await redis.get(PENDING_PINGS_KEY)
    return max(int(pending or 0), 0)


async def get_entry_backlog(redis: Redis) -> int:
    group_name = GROUP.encode()
    for group in await redis.xinfo_groups(STREAM):
        if group.get("name") == group_name:
            return int(group.get("lag") or 0) + int(group.get("pending") or 0)
    return 0


async def reconcile_backlog(redis: Redis) -> None:
    if await get_entry_backlog(redis) == 0 and await get_backlog(redis) != 0:
        await redis.set(PENDING_PINGS_KEY, 0)
        logger.info("pending pings counter reset")


async def claim_stale(redis: Redis, consumer: str) -> list[StreamChunk]:
    _, entries, _ = await redis.xautoclaim(
        name=STREAM,
        groupname=GROUP,
        consumername=consumer,
        min_idle_time=CLAIM_IDLE_MS,
        count=READ_COUNT,
    )
    return parse_stream_chunk(entries)


async def read_new(redis: Redis, consumer: str, entry_id: str = NEW_MESSAGES) -> list[StreamChunk]:
    response = await redis.xreadgroup(
        groupname=GROUP,
        consumername=consumer,
        streams={STREAM: entry_id},
        count=READ_COUNT,
        block=BLOCK_MS,
    )
    # RESP2 answers with one [stream_name, entries] pair per requested stream
    if not isinstance(response, list) or not response:
        return []

    _, entries = response[0]
    return parse_stream_chunk(entries)


async def ack(redis: Redis, chunks: list[StreamChunk]) -> None:
    if not chunks:
        return

    pings_count = sum(len(chunk.pings) for chunk in chunks)
    async with redis.pipeline(transaction=False) as pipe:
        await pipe.xack(STREAM, GROUP, *[chunk.entry_id for chunk in chunks])
        await pipe.decrby(PENDING_PINGS_KEY, pings_count)
        await pipe.execute()


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            name=STREAM,
            groupname=GROUP,
            id="0",
            mkstream=True,
        )
        logger.info("consumer group created", group=GROUP)
    except ResponseError as exc:
        if not str(exc).startswith(GROUP_EXISTS_PREFIX):
            raise
