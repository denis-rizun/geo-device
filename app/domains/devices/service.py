import structlog
from redis.asyncio import Redis

from app.core.config import config
from app.core.exceptions import ServiceUnavailableError
from app.domains.devices.schemas import LocationAcceptedResponse, LocationBatchRequest, LocationRequest
from app.pipeline import stream
from app.pipeline.constants import RETRY_AFTER_S
from app.pipeline.utils import Ping

logger = structlog.getLogger(__name__)


class DeviceService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def save_points(self, payload: LocationBatchRequest) -> LocationAcceptedResponse:
        backlog = await stream.get_backlog(self._redis)
        if backlog > config.ingest.BACKLOG_LIMIT:
            logger.warning("backlog limit exceeded", backlog=backlog, limit=config.ingest.BACKLOG_LIMIT)
            raise ServiceUnavailableError("Ingest backlog is full, retry later", retry_after_s=RETRY_AFTER_S)

        await stream.publish(self._redis, [self._to_ping(point) for point in payload.points])
        return LocationAcceptedResponse(accepted=len(payload.points), backlog=backlog)

    @staticmethod
    def _to_ping(point: LocationRequest) -> Ping:
        return Ping(device_id=point.device_id, lat=point.lat, lon=point.lon, recorded_at=point.recorded_at)
