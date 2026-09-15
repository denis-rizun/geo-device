
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import config

engine = create_async_engine(
    url=config.database.get_url(),
    pool_size=config.database.POOL_SIZE,
    max_overflow=config.database.MAX_OVERFLOW,
    pool_timeout=config.database.POOL_TIMEOUT_S,
    echo=config.ENV == "DEV",
    connect_args={
        "timeout": config.database.CONNECT_TIMEOUT_S,
        "command_timeout": config.database.COMMAND_TIMEOUT_S,
    },
)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine() -> None:
    await engine.dispose()


class Base(DeclarativeBase):
    pass
