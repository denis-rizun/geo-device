from collections import defaultdict

import orjson
import structlog
from redis.asyncio import Redis

from app.pipeline.utils import Ping, ZoneHit
from app.realtime.constants import (
    ALERT_CHANNEL,
    ALERT_MESSAGE_TYPE,
    POSITION_CHANNEL,
    POSITION_MESSAGE_TYPE,
)

logger = structlog.getLogger(__name__)


async def publish_alerts(redis: Redis, hits: list[ZoneHit]) -> int:
    if not hits:
        return 0

    by_user: dict[str, list[ZoneHit]] = defaultdict(list)
    for hit in hits:
        by_user[hit.user_id].append(hit)

    async with redis.pipeline(transaction=False) as pipe:
        for user_id, user_hits in by_user.items():
            payload = orjson.dumps({"type": ALERT_MESSAGE_TYPE, "alerts": user_hits})
            await pipe.publish(ALERT_CHANNEL.format(user_id=user_id), payload)

        await pipe.execute()
    return len(hits)


async def publish_positions(redis: Redis, positions: list[Ping]) -> int:
    if not positions:
        return 0

    payload = orjson.dumps({"type": POSITION_MESSAGE_TYPE, "positions": [position.to_json() for position in positions]})
    await redis.publish(POSITION_CHANNEL, payload)
    return len(positions)
