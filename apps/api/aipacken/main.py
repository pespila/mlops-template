from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from aipacken.api.routers import (
    auth,
    catalog,
    datasets,
    deployments,
    experiments,
    health,
    internal,
    models,
    predictions,
    runs,
    sse,
)
from aipacken.config import get_settings
from aipacken.db import SessionLocal
from aipacken.scripts.seed_admin import seed_admin
from aipacken.scripts.seed_catalog import seed_catalog

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("api.startup", env=settings.platform_env)

    try:
        from aipacken.services.minio_client import ensure_buckets

        ensure_buckets()
    except Exception as exc:  # noqa: BLE001 — we want the app to keep starting even if MinIO is down
        logger.warning("api.startup.minio_unavailable", error=str(exc))

    try:
        async with SessionLocal() as db:
            await seed_admin(db)
            await seed_catalog(db)
    except Exception as exc:  # noqa: BLE001 — migrations may not have run yet
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
        same_site="lax",
        https_only=settings.platform_env == "prod",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    app.include_router(internal.router, prefix="/api")

    app.include_router(sse.router, prefix="/sse")

    return app


app = create_app()
