from datetime import UTC, datetime

from pydantic import Field, field_validator

from app.core.config import config
from app.core.utils import BaseSchema, DeviceId, Latitude, Longitude


class LocationRequest(BaseSchema):
    device_id: DeviceId
    lat: Latitude
    lon: Longitude
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("recorded_at")
    @classmethod
    def ensure_tz(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class LocationBatchRequest(BaseSchema):
    points: list[LocationRequest] = Field(min_length=1, max_length=config.ingest.MAX_HTTP_BATCH_SIZE)


class LocationAcceptedResponse(BaseSchema):
    accepted: int
    backlog: int  # stream entries still waiting to be written, measured before this batch


class DeviceLatest(BaseSchema):
    device_id: DeviceId
    lat: Latitude
    lon: Longitude
    recorded_at: datetime
