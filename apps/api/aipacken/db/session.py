from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from aipacken.config import get_settings


def _async_url(url: str) -> str:
    # psycopg3 supports async out of the box via postgresql+psycopg
    return url


settings = get_settings()
engine = create_async_engine(_async_url(settings.database_url), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
