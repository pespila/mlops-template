from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

os.environ.setdefault("PLATFORM_SECRET_KEY", "x" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Redirect the platform data volume to a per-pytest temp dir so tests that touch
# the filesystem don't need a real Docker volume.
_TEST_DATA_ROOT = tempfile.mkdtemp(prefix="aipacken-test-")
os.environ.setdefault("DATA_ROOT", _TEST_DATA_ROOT)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from aipacken import db as db_module  # noqa: E402
from aipacken.db import get_db  # noqa: E402
from aipacken.db.base import Base  # noqa: E402
from aipacken.db import models as _models  # noqa: E402,F401  — register tables


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[Any]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # JSONB → JSON fallback for sqlite: replace the dialect-specific JSONB columns.
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import JSON

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: Any) -> Any:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session

    # Patch SessionLocal used by lifespan seeders so they hit the sqlite test DB.
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    from aipacken import main as main_module

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)

    # Disable Arq enqueue during tests — replaced with an AsyncMock.
    from aipacken.jobs import queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue", AsyncMock(return_value="job-stub"))

    from aipacken.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_login(client: AsyncClient) -> AsyncClient:
    r = await client.post(
        "/api/auth/login",
        json={"email": "admin@local", "password": "change-me"},
    )
    assert r.status_code == 200, r.text
    return client
