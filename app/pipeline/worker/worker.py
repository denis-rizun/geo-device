import asyncio

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from structlog.stdlib import BoundLogger

from app.core.config import config
from app.core.db import async_session
from app.pipeline import stream
from app.pipeline.constants import (
    CLAIM_INTERVAL_S,
    CLAIM_JITTER_S,
    NEW_MESSAGES,
    PENDING_MESSAGES,
    POSITION_FLUSH_JITTER_S,
    RETRY_BACKOFF_MAX_S,
    RETRY_BACKOFF_S,
)
from app.pipeline.matcher import match_zones
from app.pipeline.presence import filter_new_entries
from app.pipeline.utils import Backoff, Ping, StreamChunk, Ticker, ZoneHit
from app.pipeline.writer import write_pings
from app.realtime.events import publish_alerts, publish_positions

logger = structlog.getLogger(__name__)


class IngestWorker:
    def __init__(self, redis: Redis, worker_id: int) -> None:
        self._redis = redis
        self._consumer = f"ingest-{worker_id}"
        self._logger: BoundLogger = logger.bind(consumer=self._consumer)
        self._backoff = Backoff(RETRY_BACKOFF_S, RETRY_BACKOFF_MAX_S)
        self._claim_ticker = Ticker(CLAIM_INTERVAL_S, CLAIM_JITTER_S)
        self._position_ticker = Ticker(config.ingest.POSITION_FLUSH_INTERVAL_S, POSITION_FLUSH_JITTER_S)
        self._positions: dict[str, Ping] = {}

    async def run(self) -> None:
        self._logger.info("ingest worker started")
        try:
            while True:
                await self._step()
        except asyncio.CancelledError:
            await self._drain()
            self._logger.info("ingest worker stopped")
            raise

    async def _step(self) -> None:
        try:
            succeeded = await self._process_once()
        except (RedisError, OSError) as exc:
            self._logger.warning("ingest loop failed", error=str(exc))
            succeeded = False

        if succeeded:
            self._backoff.reset()
            return

        delay = await self._backoff.sleep()
        self._logger.warning("backed off", backoff_s=delay)

    async def _process_once(self) -> bool:
        claimed = await self._claim_stale() if self._claim_ticker.due() else True

        chunks = await stream.read_new(self._redis, self._consumer)
        flushed = await self._flush(chunks) if chunks else True
        await self._broadcast_positions()

        return claimed and flushed

    async def _flush(self, chunks: list[StreamChunk]) -> bool:
        pings = [ping for chunk in chunks for ping in chunk.pings]
        if not pings:
            return True

        try:
            async with async_session() as session:
                written = await write_pings(session, pings)
                hits = await match_zones(session, pings)
                await session.commit()

        except (SQLAlchemyError, OSError) as exc:
            self._logger.warning(
                "flush failed",
                pings_length=len(pings),
                error=type(exc).__name__,
                error_detail=str(exc),
            )
            return False

        self._positions.update({ping.device_id: ping for ping in pings})

        alerts_count = await self._alert(hits)
        await stream.ack(self._redis, [chunk.entry_id for chunk in chunks])
        self._logger.debug("flushed", written=written, hits=len(hits), alerts=alerts_count)
        return True

    async def _alert(self, hits: list[ZoneHit]) -> int:
        try:
            entries = await filter_new_entries(self._redis, hits)
            return await publish_alerts(self._redis, entries)
        except (RedisError, OSError) as exc:
            self._logger.warning("alerting failed", error=type(exc).__name__, error_detail=str(exc))
            return 0

    async def _broadcast_positions(self) -> None:
        if not self._positions or not self._position_ticker.due():
            return

        positions = list(self._positions.values())
        self._positions.clear()
        try:
            await publish_positions(self._redis, positions)
        except (RedisError, OSError) as exc:
            self._logger.warning(
                "position broadcast failed",
                positions_length=len(positions),
                error=type(exc).__name__,
                error_detail=str(exc),
            )

    async def _claim_stale(self) -> bool:
        stale = await stream.claim_stale(self._redis, self._consumer)
        if not stale:
            return True

        self._logger.warning("claimed stale chunks", stale_chunks=len(stale))
        return await self._flush(stale)

    async def _drain(self) -> None:
        self._logger.info("draining before shutdown")
        try:
            async with asyncio.timeout(config.ingest.DRAIN_TIMEOUT_S):
                for start_id in (PENDING_MESSAGES, NEW_MESSAGES):
                    while chunks := await stream.read_new(self._redis, self._consumer, start_id):
                        if not await self._flush(chunks):
                            self._logger.warning("drain aborted, flush failed")
                            return
        except TimeoutError:
            self._logger.warning("drain timed out", timeout_s=config.ingest.DRAIN_TIMEOUT_S)


async def ingest_worker(redis: Redis, worker_id: int) -> None:
    worker = IngestWorker(redis, worker_id)
    await worker.run()
