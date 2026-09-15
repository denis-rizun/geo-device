from typing import Any, cast

from sqlalchemy import CursorResult, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import SRID
from app.domains.devices.models import LocationPing
from app.pipeline.utils import Ping


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
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount


def _to_ewkt(ping: Ping) -> str:
    return f"SRID={SRID};POINT({ping.lon} {ping.lat})"
