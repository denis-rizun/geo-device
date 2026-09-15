from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import SRID
from app.pipeline.utils import Ping, ZoneHit

_MATCH_SQL = text(f"""
    SELECT DISTINCT ON (g.id, b.device_id)
           g.user_id,
           g.id AS geozone_id,
           g.name AS geozone_name,
           b.device_id,
           b.lat,
           b.lon,
           b.recorded_at
    FROM unnest(
             :device_ids::text[],
             :lons::float8[],
             :lats::float8[],
             :recorded_ats::timestamptz[]
         ) AS b(device_id, lon, lat, recorded_at)
    JOIN geozones g
      ON ST_DWithin(
             g.center,
             ST_SetSRID(ST_MakePoint(b.lon, b.lat), {SRID})::geography,
             g.radius_m
         )
    ORDER BY g.id, b.device_id, b.recorded_at DESC
""")


async def match_zones(session: AsyncSession, pings: list[Ping]) -> list[ZoneHit]:
    if not pings:
        return []

    params = {
        "device_ids": [ping.device_id for ping in pings],
        "lons": [ping.lon for ping in pings],
        "lats": [ping.lat for ping in pings],
        "recorded_ats": [ping.recorded_at for ping in pings],
    }
    rows = (await session.execute(_MATCH_SQL, params)).all()
    return [ZoneHit(*row) for row in rows]
