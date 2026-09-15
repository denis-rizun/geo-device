from collections import defaultdict

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from app.core.config import config
from app.pipeline.constants import DEVICE_ZONES_KEY, SYNC_ZONES_LUA
from app.pipeline.utils import ZoneHit

_script: AsyncScript | None = None


def get_script(redis: Redis) -> AsyncScript:
    global _script
    if not _script:
        _script = redis.register_script(SYNC_ZONES_LUA)
    return _script


async def filter_new_entries(redis: Redis, hits: list[ZoneHit], device_ids: list[str]) -> list[ZoneHit]:
    if not device_ids:
        return []

    hits_by_device: dict[str, dict[bytes, ZoneHit]] = defaultdict(dict)
    for hit in hits:
        hits_by_device[hit.device_id][str(hit.geozone_id).encode()] = hit

    script = get_script(redis)
    devices = list(dict.fromkeys(device_ids))

    async with redis.pipeline(transaction=False) as pipe:
        for device_id in devices:
            await script(
                keys=[DEVICE_ZONES_KEY.format(device_id=device_id)],
                args=[config.ingest.ZONE_ENTRY_TTL_S, *hits_by_device.get(device_id, {})],
                client=pipe,
            )
        results = await pipe.execute()

    entries: list[ZoneHit] = []
    for device_id, entered in zip(devices, results, strict=True):
        zones = hits_by_device.get(device_id, {})
        entries.extend(zones[zone_id] for zone_id in entered if zone_id in zones)
    return entries
