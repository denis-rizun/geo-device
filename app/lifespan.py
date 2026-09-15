import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import config
from app.core.db import dispose_engine
from app.core.logger import configure_logging
from app.core.redis_client import close_redis, init_redis
from app.pipeline import stream
from app.pipeline.worker import ingest_worker
from app.realtime.subscriber import close_subscriber, init_subscriber

logger = structlog.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()

    client = await init_redis()
    await stream.ensure_group(client)
    await init_subscriber(client)

    tasks = [
        asyncio.create_task(ingest_worker(client, i), name=f"ingest-worker-{i}") for i in range(config.ingest.WORKERS)
    ]
    logger.info("application started", env=config.ENV, version=config.api.VERSION)
    logger.info("started ingest workers", workers_count=config.ingest.WORKERS)

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        await close_subscriber()
        await close_redis()
        await dispose_engine()
        logger.info("application ended")
