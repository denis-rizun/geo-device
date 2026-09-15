from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

import structlog
from fastapi import FastAPI

from app.core.config import config
from app.core.db import dispose_engine
from app.core.logger import configure_logging
from app.core.redis_client import close_redis, init_redis
from app.pipeline import stream
from app.pipeline.retention import retention_worker
from app.pipeline.worker.lifecycle import Supervisor
from app.pipeline.worker.worker import IngestWorker
from app.realtime.subscriber import close_subscriber, init_subscriber

logger = structlog.getLogger(__name__)


def _heartbeat_of(worker: IngestWorker) -> float:
    return worker.heartbeat


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()

    client = await init_redis()
    await stream.ensure_group(client)
    await init_subscriber(client)

    supervisor = Supervisor()
    for worker_id in range(config.ingest.WORKERS):
        worker = IngestWorker(client, worker_id)
        supervisor.add(f"ingest-worker-{worker_id}", worker.run, heartbeat=partial(_heartbeat_of, worker))

    supervisor.add("retention-worker", retention_worker)
    await supervisor.start()

    logger.info("application started", env=config.ENV, version=config.api.VERSION)
    logger.info("started ingest workers", workers_count=config.ingest.WORKERS)

    try:
        yield
    finally:
        await supervisor.stop()
        await close_subscriber()
        await close_redis()
        await dispose_engine()
        logger.info("application ended")
