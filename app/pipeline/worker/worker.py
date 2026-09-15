import asyncio
from time import monotonic

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

PIPELINE_ERRORS = (SQLAlchemyError, RedisError, OSError, TimeoutError)


class IngestWorker:
    def __init__(self, redis: Redis, worker_id: int) -> None:
        self.heartbeat = monotonic()
        self._redis = redis
        self._consumer = f"ingest-{worker_id}"
        self._logger: BoundLogger = logger.bind(consumer=self._consumer)
        self._backoff = Backoff(RETRY_BACKOFF_S, RETRY_BACKOFF_MAX_S)
        self._claim_ticker = Ticker(CLAIM_INTERVAL_S, CLAIM_JITTER_S)
        self._position_ticker = Ticker(config.ingest.POSITION_FLUSH_INTERVAL_S, POSITION_FLUSH_JITTER_S)
        self._positions: dict[str, Ping] = {}

    async def run(self) -> None:
        self._logger.info("ingest worker started")
        self.heartbeat = monotonic()
        try:
            while True:
                await self._step()
                self.heartbeat = monotonic()
        except asyncio.CancelledError:
            await self._drain()
            self._logger.info("ingest worker stopped")
            raise

    async def _step(self) -> None:
        try:
            succeeded = await self._process_once()
        except PIPELINE_ERRORS as exc:
            self._logger.warning("ingest loop failed", error=str(exc))
            succeeded = False

        if succeeded:
            self._backoff.reset()
            return

        delay = await self._backoff.sleep()
        self._logger.warning("backed off", backoff_s=delay)

    async def _process_once(self) -> bool:
        claimed = True
        if self._claim_ticker.due():
            claimed = await self._claim_stale()
            await stream.reconcile_backlog(self._redis)

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

        except PIPELINE_ERRORS as exc:
            self._logger.warning(
                "flush failed",
                pings_length=len(pings),
                error=str(exc),
            )
            return False

        self._positions.update({ping.device_id: ping for ping in pings})

        alerts_count = await self._alert(hits, [ping.device_id for ping in pings])
        await stream.ack(self._redis, chunks)
        self._logger.debug("flushed", written=written, hits=len(hits), alerts=alerts_count)
        return True

    async def _alert(self, hits: list[ZoneHit], device_ids: list[str]) -> int:
        try:
            entries = await filter_new_entries(self._redis, hits, device_ids)
            return await publish_alerts(self._redis, entries)
        except (RedisError, OSError, TimeoutError) as exc:
            self._logger.warning("alerting failed", error=str(exc))
            return 0

    async def _broadcast_positions(self) -> None:
        if not self._positions or not self._position_ticker.due():
            return

        positions = list(self._positions.values())
        self._positions.clear()
        try:
            await publish_positions(self._redis, positions)
        except (RedisError, OSError, TimeoutError) as exc:
            self._logger.warning(
                "position broadcast failed",
                positions_length=len(positions),
                error=str(exc),
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
        except PIPELINE_ERRORS as exc:
            self._logger.warning("drain failed", error=str(exc))
