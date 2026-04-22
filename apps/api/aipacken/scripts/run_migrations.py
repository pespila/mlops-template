"""Entry point for the ``migrate`` init-container.

Invocation:
    python -m aipacken.scripts.run_migrations

Runs Alembic ``upgrade head`` against ``settings.database_url``, wrapped
in a Postgres advisory lock so rolling deploys with >1 api replica (or a
concurrent ``migrate`` re-run) don't race on DDL. Exits 0 on success,
non-zero otherwise — suitable as a one-shot compose service with
``restart: on-failure``.

Same function is still called opportunistically from the FastAPI
lifespan so a fresh ``make up`` without the migrate service still boots.
In a prod-style rollout the init-container owns the upgrade; the api
lifespan call becomes a no-op (head already == current).
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from aipacken.config import get_settings

logger = structlog.get_logger(__name__)

# Deterministic 64-bit key derived from a platform-specific string so two
# independent apps sharing a Postgres instance do not contend.
# pg_advisory_lock(bigint): we pack the key as a single bigint
# 0x4149504143454E21 ("AIPACEN!" as bytes).
_ADVISORY_LOCK_KEY = 0x4149504143454E21


def _app_root() -> Path:
    # /app inside the container: apps/api/aipacken/scripts/run_migrations.py
    # → app_root is apps/api (where alembic.ini + migrations/ live).
    return Path(__file__).resolve().parent.parent.parent


def run_migrations() -> None:
    app_root = _app_root()
    cfg = Config(str(app_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(app_root / "migrations"))
    url = get_settings().database_url
    cfg.set_main_option("sqlalchemy.url", url)

    if not url.startswith("postgresql"):
        command.upgrade(cfg, "head")
        return

    sync_url = url.replace("+asyncpg", "").replace("+async", "")
    eng = create_engine(sync_url, pool_pre_ping=True)
    with eng.begin() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        try:
            command.upgrade(cfg, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
    eng.dispose()


def main() -> int:
    try:
        run_migrations()
    except Exception as exc:  # noqa: BLE001 — top-level CLI, exit 1 with structured log
        logger.error("migrate.failed", error=str(exc))
        return 1
    logger.info("migrate.ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
