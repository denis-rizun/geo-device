from collections.abc import AsyncGenerator

import psycopg
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.core.config import config
from app.core.db import Base
from app.domains.devices import models as _device_models
from app.domains.geozones import models as _geozone_models

_ = (_device_models, _geozone_models)

ADMIN_DATABASE = "postgres"
POSTGIS_EXTENSION = "CREATE EXTENSION IF NOT EXISTS postgis"


def _run_admin(statement: str) -> None:
    with psycopg.connect(config.database.get_test_url(None, ADMIN_DATABASE), autocommit=True) as connection:
        connection.execute(statement)


def _database_exists() -> bool:
    with psycopg.connect(config.database.get_test_url(None, ADMIN_DATABASE)) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (config.database.TEST_DATABASE,)
        ).fetchone()
    return row is not None


async def _create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(POSTGIS_EXTENSION))
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session")
def test_database() -> str:
    if not config.database.TEST_DATABASE or config.database.TEST_DATABASE == config.database.DATABASE:
        pytest.fail("POSTGRES_TEST_DATABASE must be set and differ from POSTGRES_DATABASE")

    return config.database.TEST_DATABASE


@pytest.fixture(scope="session")
async def test_engine(test_database: str) -> AsyncGenerator[AsyncEngine]:
    if _database_exists():
        _run_admin(f'DROP DATABASE "{test_database}" WITH (FORCE)')
    _run_admin(f'CREATE DATABASE "{test_database}"')

    engine = create_async_engine(config.database.get_test_url())
    await _create_schema(engine)
    yield engine

    await engine.dispose()
    _run_admin(f'DROP DATABASE "{test_database}" WITH (FORCE)')


@pytest.fixture
async def db_connection(test_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture(scope="session")
async def test_redis() -> AsyncGenerator[Redis]:
    if config.redis.TEST_DB == config.redis.DB:
        pytest.fail("REDIS_TEST_DB must differ from REDIS_DB")

    client = Redis.from_url(config.redis.get_test_url(), decode_responses=False)
    yield client

    await client.aclose()


@pytest.fixture
async def redis(test_redis: Redis) -> AsyncGenerator[Redis]:
    await test_redis.flushdb()
    yield test_redis
    await test_redis.flushdb()
