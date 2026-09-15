from redis.asyncio import Redis

from app.core.config import config
from app.pipeline.constants import ZONE_ENTRY_KEY
from app.pipeline.utils import ZoneHit


async def filter_new_entries(redis: Redis, hits: list[ZoneHit]) -> list[ZoneHit]:
    if not hits:
        return []

    ttl = config.ingest.ZONE_ENTRY_TTL_S
    async with redis.pipeline(transaction=False) as pipe:
        for hit in hits:
            key = ZONE_ENTRY_KEY.format(device_id=hit.device_id, geozone_id=hit.geozone_id)
            await pipe.set(key, 1, nx=True, ex=ttl)
            await pipe.expire(key, ttl)

        results = await pipe.execute()

    return [hit for hit, is_new in zip(hits, results[::2], strict=True) if is_new]
