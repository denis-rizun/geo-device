import asyncio
import random
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any, Self

import orjson
import structlog

from app.pipeline.constants import PAYLOAD_FIELD

logger = structlog.getLogger(__name__)


@dataclass(frozen=True)
class Ping:
    device_id: str
    lat: float
    lon: float
    recorded_at: datetime

    def to_json(self) -> tuple[str, float, float, str]:
        return self.device_id, self.lat, self.lon, self.recorded_at.isoformat()

    @classmethod
    def from_json(cls, data: tuple[str, float, float, str]) -> Self:
        device_id, lat, lon, recorded_at = data
        return cls(device_id=device_id, lat=lat, lon=lon, recorded_at=datetime.fromisoformat(recorded_at))


def encode_pings(pings: list[Ping]) -> bytes:
    return orjson.dumps([ping.to_json() for ping in pings])


def decode_pings(raw: bytes) -> list[Ping]:
    return [Ping.from_json(data) for data in orjson.loads(raw)]


@dataclass(frozen=True)
class StreamChunk:
    entry_id: bytes
    pings: list[Ping]


def parse_stream_chunk(entries: list[Any]) -> list[StreamChunk]:
    chunks: list[StreamChunk] = []
    for entry_id, fields in entries:
        raw = fields.get(PAYLOAD_FIELD)
        if not raw:
            logger.warning("malformed stream entry skipping", entry_id=entry_id)
            continue

        chunks.append(StreamChunk(entry_id=entry_id, pings=decode_pings(raw)))
    return chunks


class Backoff:
    def __init__(self, start: float, limit: float) -> None:
        self._start = start
        self._limit = limit
        self._delay = 0.0

    def reset(self) -> None:
        self._delay = 0.0

    async def sleep(self) -> float:
        self._delay = self._start if not self._delay else min(self._delay * 2, self._limit)
        await asyncio.sleep(self._delay)
        return self._delay


class Ticker:
    def __init__(self, interval: float, jitter: float) -> None:
        self._interval = interval
        self._jitter = jitter
        self._next_at = monotonic() + self._period

    @property
    def _period(self) -> float:
        return self._interval + random.uniform(0.0, self._jitter)

    def due(self) -> bool:
        now = monotonic()
        if now < self._next_at:
            return False

        self._next_at = now + self._period
        return True


@dataclass(frozen=True)
class ZoneHit:
    user_id: str
    geozone_id: int
    geozone_name: str
    device_id: str
    lat: float
    lon: float
    recorded_at: datetime
