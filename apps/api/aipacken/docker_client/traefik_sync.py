"""Idempotent writer for Traefik's dynamic routes file for model deployments.

The platform's Traefik runs with the file provider only (no Docker provider,
because mounting the Docker socket into the proxy would double the host-root
RCE surface). Every active Deployment needs a router + service entry that
maps ``/models/<slug>`` to the per-model serving container.

This module rewrites ``<TRAEFIK_DYNAMIC_DIR>/models.yml`` atomically from
the current set of Deployment rows. Call on deploy (after the container is
up) and on teardown (after the container is stopped). Static routes for the
api + frontend live in a sibling ``routes.yml`` and are not touched here.

Closes infra.md P0 #1 ('Traefik provider mismatch — dynamic model routes
are dead code').
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import Deployment

logger = structlog.get_logger(__name__)


def _dynamic_dir() -> Path:
    return Path(os.environ.get("TRAEFIK_DYNAMIC_DIR", "/etc/traefik/dynamic"))


def _build_config(deployments: list[Deployment]) -> dict[str, object]:
    """Shape the Traefik dynamic-config dict. Uses JSON-compatible YAML shape."""
    routers: dict[str, object] = {}
    services: dict[str, object] = {}
    for dep in deployments:
        # Only route deployments that actually have a reachable container.
        # ``deploying`` / ``failed`` / ``stopped`` do not get a route.
        if dep.status not in ("active", "unhealthy") or not dep.container_id:
            continue
        name = f"model-{dep.slug}"
        routers[name] = {
            "rule": f"PathPrefix(`/models/{dep.slug}`)",
            "entryPoints": ["web"],
            "service": name,
            "priority": 50,  # above frontend (1), below api (100)
            "middlewares": [f"{name}-strip"],
        }
        services[name] = {
            "loadBalancer": {
                "servers": [{"url": f"http://{name}:8000"}],
            }
        }
    middlewares: dict[str, object] = {
        f"model-{dep.slug}-strip": {
            "stripPrefix": {"prefixes": [f"/models/{dep.slug}"]},
        }
        for dep in deployments
        if dep.status in ("active", "unhealthy") and dep.container_id
    }
    return {
        "http": {
            "routers": routers,
            "services": services,
            "middlewares": middlewares,
        }
    }


def _to_yaml(cfg: dict[str, object]) -> str:
    """Serialize to YAML via JSON (Traefik accepts JSON under a .yml filename).

    Avoids adding a PyYAML dep. Traefik parses both formats from .yml / .yaml
    / .json files when the filename extension is .yml/.yaml — JSON is a
    strict subset of YAML 1.2, so a JSON document in a .yml file is valid
    YAML. If that ever changes upstream, swap this for yaml.safe_dump.
    """
    return json.dumps(cfg, indent=2, sort_keys=True)


async def sync_model_routes(db: AsyncSession) -> Path:
    """Rewrite models.yml from the current Deployment table. Returns the path."""
    dyn = _dynamic_dir()
    dyn.mkdir(parents=True, exist_ok=True)

    rows = (await db.execute(select(Deployment))).scalars().all()
    cfg = _build_config(list(rows))

    dest = dyn / "models.yml"
    # Atomic write: tempfile in the same dir + os.replace. Traefik's file
    # watcher is debounced and will not see a half-written file.
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=dyn, prefix=".models-", suffix=".tmp"
    ) as fp:
        fp.write(_to_yaml(cfg))
        tmp_path = Path(fp.name)
    os.replace(tmp_path, dest)
    logger.info("traefik.sync", active=len(cfg["http"]["routers"]), path=str(dest))  # type: ignore[index]
    return dest
