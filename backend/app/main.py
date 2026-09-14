import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import config
from app.core.db import dispose_engine
from app.core.exceptions import register_exception_handler
from app.core.logger import configure_logging
from app.core.redis_client import close_redis, init_redis
from app.domains.devices.router import router as device_router
from app.domains.geozones.router import router as geozone_router
from app.pipeline import stream
from app.pipeline.worker import ingest_worker


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger = structlog.get_logger()

    client = await init_redis()
    await stream.ensure_group(client)

    tasks = [
        asyncio.create_task(ingest_worker(client, i), name=f"ingest-worker-{i}") for i in range(config.ingest.WORKERS)
    ]
    logger.info("application started", env=config.ENV, version=config.api.VERSION)
    logger.info("started ingest workers", workers_count=len(tasks))

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        await close_redis()
        await dispose_engine()
        logger.info("application ended")


app = FastAPI(
    title=config.api.NAME,
    version=config.api.VERSION,
    lifespan=lifespan,
    root_path="/api/v1",
    openapi_url=None if config.ENV == "PROD" else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.ALLOWED_HOSTS,
    allow_credentials=config.api.ALLOW_CREDENTIALS,
    allow_methods=config.api.ALLOWED_METHODS,
    allow_headers=config.api.ALLOWED_HEADERS,
)
app.include_router(device_router)
app.include_router(geozone_router)

register_exception_handler(app)


@app.get(path="/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
