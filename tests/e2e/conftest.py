from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.dependencies import get_session
from app.main import app

BASE_URL = "http://testserver/api/v1"


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as http_client:
        yield http_client


@pytest.fixture
async def client_with_db(client: AsyncClient, db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
async def client_with_redis(client: AsyncClient, redis: Redis) -> AsyncGenerator[AsyncClient]:
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_redis, None)
