import asyncio
import random
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
    RETRY_BACKOFF_MAX_S,
    RETRY_BACKOFF_S,
)
from app.pipeline.utils import StreamChunk
from app.pipeline.writer import write_pings

logger = structlog.getLogger(__name__)


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


class IngestWorker:
    def __init__(self, redis: Redis, worker_id: int) -> None:
        self._redis = redis
        self._consumer = f"ingest-{worker_id}"
        self._logger: BoundLogger = logger.bind(consumer=self._consumer)
        self._backoff = Backoff(RETRY_BACKOFF_S, RETRY_BACKOFF_MAX_S)
        self._ticker = Ticker(CLAIM_INTERVAL_S, CLAIM_JITTER_S)

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
            ok = True
            if self._ticker.due():
                ok = await self._claim_stale()

            chunks = await stream.read_new(self._redis, self._consumer)
            if chunks:
                ok = await self._flush(chunks) and ok
        except (RedisError, SQLAlchemyError, OSError) as exc:
            self._logger.warning("ingest loop failed", error=type(exc).__name__, error_detail=str(exc))
            ok = False

        if ok:
            self._backoff.reset()
        else:
            self._logger.warning("backing off", backoff_s=await self._backoff.sleep())

    async def _flush(self, chunks: list[StreamChunk]) -> bool:
        pings = [ping for chunk in chunks for ping in chunk.pings]
        if not pings:
            return True

        try:
            async with async_session() as session:
                written = await write_pings(session, pings)
                await session.commit()
        except (SQLAlchemyError, OSError) as exc:
            self._logger.warning(
                "flush failed",
                pings_length=len(pings),
                error=type(exc).__name__,
                error_detail=str(exc),
            )
            return False

        await stream.ack(self._redis, [chunk.entry_id for chunk in chunks])
        self._logger.debug("flushed", written=written)
        return True

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
