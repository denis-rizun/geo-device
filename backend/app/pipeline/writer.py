from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.devices.models import LocationPing
from app.pipeline.utils import Ping

SRID = 4326


async def write_pings(session: AsyncSession, pings: list[Ping]) -> int:
    if not pings:
        return 0

    stmt = insert(LocationPing).values(
        [
            {
                "device_id": ping.device_id,
                "point": _to_ewkt(ping),
                "recorded_at": ping.recorded_at,
            }
            for ping in pings
        ]
    )
    result = await session.execute(stmt)
    return result.rowcount


def _to_ewkt(ping: Ping) -> str:
    return f"SRID={SRID};POINT({ping.lon} {ping.lat})"
