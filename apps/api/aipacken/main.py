from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from aipacken.api.routers import health
from aipacken.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("api.startup", env=settings.platform_env)
    yield
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

    app.include_router(health.router, prefix="/api")

    return app


app = create_app()
