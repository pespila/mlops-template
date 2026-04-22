from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

os.environ.setdefault("PLATFORM_SECRET_KEY", "x" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Pin the admin identity to what the tests assert against — the dev `.env`
# in the repo ships `PLATFORM_ADMIN_EMAIL=admin@aipacken.local`, which
# pydantic-settings would otherwise pick up and cause every auth'd test to
# 401 on the hard-coded `admin@local`. Use explicit assignment, not
# setdefault, so we beat the .env value that's already in process env.
os.environ["PLATFORM_ADMIN_EMAIL"] = "admin@local"
os.environ["PLATFORM_ADMIN_PASSWORD"] = "change-me"
# Redirect the platform data volume to a per-pytest temp dir so tests that touch
# the filesystem don't need a real Docker volume.
_TEST_DATA_ROOT = tempfile.mkdtemp(prefix="aipacken-test-")
os.environ.setdefault("DATA_ROOT", _TEST_DATA_ROOT)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aipacken import db as db_module
from aipacken.db import get_db
from aipacken.db import models as _models  # noqa: F401  — register tables
from aipacken.db.base import Base


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[Any]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # JSONB → JSON fallback is now handled at the column type level via
    # `JsonColumn = JSON().with_variant(JSONB, "postgresql")` in db/models.py,
    # so no runtime type patching is needed here any more.
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: Any) -> Any:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(
    session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session

    # Patch SessionLocal used by lifespan seeders so they hit the sqlite test DB.
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    from aipacken import main as main_module

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)

    # Disable Arq enqueue during tests — replaced with an AsyncMock. Routers
    # pull `enqueue` in as `from aipacken.jobs.queue import enqueue`, which
    # binds it locally, so we need to patch both the source module AND every
    # router's local binding (otherwise the real enqueue fires → opens a
    # Redis connection → "Event loop is closed" noise at teardown).
    from aipacken.api.routers import datasets as _rd_datasets
    from aipacken.api.routers import deployments as _rd_deployments
    from aipacken.api.routers import packages as _rd_packages
    from aipacken.api.routers import runs as _rd_runs
    from aipacken.jobs import queue as queue_module

    _enqueue_stub = AsyncMock(return_value="job-stub")
    monkeypatch.setattr(queue_module, "enqueue", _enqueue_stub)
    for _mod in (_rd_datasets, _rd_deployments, _rd_packages, _rd_runs):
        monkeypatch.setattr(_mod, "enqueue", _enqueue_stub)

    # Rate limiter's dependency was baked at router import time; the
    # cleanest stub is the Redis handle it calls — swap for an
    # AsyncMock that reports count=1 on every hit so no limit trips.
    from aipacken.api import ratelimit as _rl

    _fake_redis = AsyncMock()
    _fake_redis.incr = AsyncMock(return_value=1)
    _fake_redis.expire = AsyncMock(return_value=True)
    monkeypatch.setattr(_rl, "get_redis", lambda: _fake_redis)

    from aipacken.main import create_app, lifespan

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    # httpx ASGITransport doesn't drive ASGI lifespan events, so seed_admin /
    # seed_catalog in the app's lifespan never fire. Enter the lifespan
    # context manually so the test DB is populated before requests land.
    async with lifespan(app):
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


@pytest_asyncio.fixture
async def member_user(session_factory: Any) -> dict[str, str]:
    """Create a second (non-admin) user directly in the test DB.

    Yields a dict with ``email`` and ``password`` so tests can log in
    as a tenant-scoped member and assert the authz chain returns 404
    (never 200, never 403) for cross-user resource probes.
    """
    from aipacken.db.models import User
    from aipacken.services.auth import hash_password

    email = "member@local"
    password = "member-secret"
    async with session_factory() as session:
        u = User(
            email=email,
            password_hash=hash_password(password),
            role="member",
            full_name="Test Member",
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        user_id = u.id
    return {"email": email, "password": password, "id": user_id}


@pytest_asyncio.fixture
async def member_client(client: AsyncClient, member_user: dict[str, str]) -> AsyncClient:
    """An authenticated AsyncClient for the member fixture above."""
    r = await client.post(
        "/api/auth/login",
        json={"email": member_user["email"], "password": member_user["password"]},
    )
    assert r.status_code == 200, r.text
    return client
