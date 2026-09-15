import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import Delete, delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import config
from app.core.db import engine
from app.domains.devices.models import LocationPing
from app.pipeline.constants import RETENTION_MAX_PASSES

logger = structlog.getLogger(__name__)


def _delete_batch(cutoff: datetime, batch_size: int) -> Delete:
    expired = select(LocationPing.id).where(LocationPing.recorded_at < cutoff).limit(batch_size).scalar_subquery()
    return delete(LocationPing).where(LocationPing.id.in_(expired))


async def purge_expired_pings() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=config.ingest.RETENTION_DAYS)
    batch_size = config.ingest.RETENTION_BATCH_SIZE
    stmt = _delete_batch(cutoff, batch_size)
    deleted = 0

    for _ in range(RETENTION_MAX_PASSES):
        async with engine.begin() as connection:
            removed = (await connection.execute(stmt)).rowcount

        deleted += removed
        if removed < batch_size:
            break

    if deleted:
        logger.info("purged expired pings", deleted=deleted, retention_days=config.ingest.RETENTION_DAYS)
    return deleted


async def retention_worker() -> None:
    logger.info("retention worker started", interval_s=config.ingest.RETENTION_INTERVAL_S)
    while True:
        await asyncio.sleep(config.ingest.RETENTION_INTERVAL_S)
        try:
            await purge_expired_pings()
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            logger.warning("retention pass failed", error=str(exc))
