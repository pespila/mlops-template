from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from aipacken.config import get_settings


def _engine_kwargs(url: str) -> dict[str, object]:
    """Pool tuning that the default (5 + 10, no recycle) does not provide.

    Sized for a single api uvicorn replica sharing its engine with the
    request handlers + the SSE router. Under the previous defaults the pool
    saturated at ~5 concurrent SSE clients. asyncpg / aiosqlite ignore
    these kwargs gracefully where they don't apply.
    """
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs.update(
            pool_size=20,
            max_overflow=20,
            pool_recycle=1800,
            pool_timeout=30,
        )
    return kwargs


settings = get_settings()
engine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
