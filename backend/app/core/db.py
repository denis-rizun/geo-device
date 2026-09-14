from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import config

engine = create_async_engine(
    url=config.database.get_url(),
    pool_size=config.database.POOL_SIZE,
    max_overflow=config.database.MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=config.ENV == "DEV",
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def dispose_engine() -> None:
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
