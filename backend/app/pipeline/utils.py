from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

import orjson
import structlog

from app.pipeline.constants import PAYLOAD_FIELD

logger = structlog.getLogger(__name__)

PingTuple = tuple[str, float, float, str]


@dataclass(frozen=True, slots=True)
class Ping:
    device_id: str
    lat: float
    lon: float
    recorded_at: datetime

    def to_json(self) -> PingTuple:
        return self.device_id, self.lat, self.lon, self.recorded_at.isoformat()

    @classmethod
    def from_json(cls, data: PingTuple) -> Self:
        device_id, lat, lon, recorded_at = data
        return cls(device_id=device_id, lat=lat, lon=lon, recorded_at=datetime.fromisoformat(recorded_at))


def encode_pings(pings: list[Ping]) -> bytes:
    return orjson.dumps([ping.to_json() for ping in pings])


def decode_pings(raw: bytes) -> list[Ping]:
    return [Ping.from_json(data) for data in orjson.loads(raw)]


@dataclass(frozen=True, slots=True)
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
