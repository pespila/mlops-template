from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from aipacken import storage
from aipacken.api.routers import (
    artifacts,
    auth,
    catalog,
    datasets,
    deployments,
    experiments,
    health,
    internal,
    models,
    packages,
    predictions,
    runs,
    sse,
)
from aipacken.config import get_settings
from aipacken.db import SessionLocal
from aipacken.scripts.seed_admin import seed_admin
from aipacken.scripts.seed_catalog import seed_catalog

logger = structlog.get_logger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations synchronously on startup.

    The app lifecycle is authoritative here — we don't want operators to
    remember a separate ``alembic upgrade head`` step.

    A pg advisory lock gates the upgrade so rolling deploys with >1 api
    replica don't race on DDL (db.md P0 "Migrations run on every replica's
    lifespan, uncoordinated"). The first replica grabs the lock, runs
    the upgrade, releases it; the others wait then find head == current.
    SQLite has no advisory-lock concept and we only ever run one API
    process against it, so we skip the lock there.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    app_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(app_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(app_root / "migrations"))
    url = get_settings().database_url
    cfg.set_main_option("sqlalchemy.url", url)

    if not url.startswith("postgresql"):
        command.upgrade(cfg, "head")
        return

    # Convert psycopg-async driver URL to a sync one for the advisory
    # lock session; Alembic itself also uses a sync engine under the
    # hood via the `sqlalchemy.url` config above.
    sync_url = url.replace("postgresql+psycopg", "postgresql+psycopg").replace("+async", "")
    # Deterministic 64-bit key derived from a platform-specific string so
    # two independent apps sharing a Postgres instance do not contend.
    # `pg_advisory_lock(bigint)` signature: we pack the key as a single
    # bigint — 0x4149504143454E21 ("AIPACEN!" as bytes).
    lock_key = 0x4149504143454E21
    eng = create_engine(sync_url, pool_pre_ping=True)
    with eng.begin() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key})
        try:
            command.upgrade(cfg, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
    eng.dispose()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    settings = get_settings()
    logger.info("api.startup", env=settings.platform_env)

    try:
        await asyncio.to_thread(_run_migrations)
        logger.info("api.startup.migrations_ok")
    except Exception as exc:
        logger.error("api.startup.migrations_failed", error=str(exc))

    try:
        storage.ensure_base_dirs()
    except Exception as exc:
        logger.warning("api.startup.storage_unavailable", error=str(exc))

    try:
        async with SessionLocal() as db:
            await seed_admin(db)
            await seed_catalog(db)
    except Exception as exc:
        logger.warning("api.startup.seed_failed", error=str(exc))

    yield

    from aipacken.services.redis_client import close_pool

    await close_pool()
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AIpacken Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.platform_secret_key,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_max_age_seconds,
        same_site="strict",
        https_only=settings.platform_env == "prod",
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(datasets.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(experiments.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(deployments.router, prefix="/api")
    app.include_router(predictions.router, prefix="/api")
    app.include_router(artifacts.router, prefix="/api")
    app.include_router(internal.router, prefix="/api")
    app.include_router(packages.router, prefix="/api")

    app.include_router(sse.router, prefix="/sse")

    # Prometheus metrics — /metrics exposes the default http_requests_total
    # + http_request_duration_seconds plus every router as a label. Addresses
    # perf.md P0 'No observability at all' as a first deliverable; fuller
    # OpenTelemetry instrumentation is tracked separately. Metrics are
    # pulled by Prometheus (or whatever /metrics scraper) over the platform
    # network; the endpoint itself does not require auth because it only
    # emits aggregate counters, never per-resource data.
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


app = create_app()
