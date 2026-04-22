from __future__ import annotations

import re
import uuid
from datetime import UTC
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.authz import (
    get_owned_deployment,
    get_owned_run,
    scope_deployment_by_user,
)
from aipacken.api.pagination import Pagination, pagination_params
from aipacken.api.ratelimit import PREDICT_LIMIT, rate_limit
from aipacken.api.schemas.deployments import (
    DeploymentCreate,
    DeploymentList,
    DeploymentRead,
    DeploymentUpdate,
    PredictResponse,
)
from aipacken.db import get_db
from aipacken.db.models import Deployment, Run, User
from aipacken.jobs.queue import enqueue
from aipacken.services import mlflow_client
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/deployments", tags=["deployments"])


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{s}-{uuid.uuid4().hex[:8]}" if s else f"model-{uuid.uuid4().hex[:8]}"


def _to_read(dep: Deployment) -> DeploymentRead:
    out = DeploymentRead.model_validate(dep)
    out.url = f"/api/deployments/{dep.id}/predict"
    return out


@router.post("", response_model=DeploymentRead, status_code=201)
async def create_deployment(
    payload: DeploymentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeploymentRead:
    """Deploy the MLflow model attached to a platform Run.

    Resolves the MLflow ModelVersion by looking up the Run's
    ``platform.run_id`` tag in the registry — the trainer registers
    exactly one version per successful run. The Deployment row
    snapshots ``(registered_model_name, version_number, mlflow_run_id,
    model_kind)`` so the serving worker can stage artifacts without a
    round-trip to MLflow.
    """
    run = await get_owned_run(db, payload.run_id, user)

    mlflow_run = mlflow_client.find_run_by_platform_id(run.id)
    if mlflow_run is None:
        raise HTTPException(status_code=404, detail="mlflow_run_not_found")

    # Find the MLflow ModelVersion produced by this run. The trainer
    # tags it with ``platform.run_id``; we search for matching versions
    # across every registered model (there's only one per run in practice).
    candidate_name: str | None = None
    candidate_version: int | None = None
    tags = dict(mlflow_run.data.tags or {})
    model_kind = tags.get("platform.model_kind") or "sklearn"
    registered_name_tag = tags.get("platform.registered_model_name")
    if registered_name_tag:
        mvs = mlflow_client.search_model_versions(registered_name_tag)
        for mv in mvs:
            if mv.run_id == mlflow_run.info.run_id:
                candidate_name = registered_name_tag
                candidate_version = int(mv.version)
                break
    if candidate_name is None:
        # Fall back to a wider scan.
        for rm in mlflow_client.list_registered_models():
            for mv in mlflow_client.search_model_versions(rm.name):
                if mv.run_id == mlflow_run.info.run_id:
                    candidate_name = rm.name
                    candidate_version = int(mv.version)
                    break
            if candidate_name is not None:
                break
    if candidate_name is None or candidate_version is None:
        raise HTTPException(status_code=409, detail="run_has_no_registered_model_version")

    dep = Deployment(
        run_id=run.id,
        mlflow_run_id=mlflow_run.info.run_id,
        registered_model_name=candidate_name,
        version_number=candidate_version,
        model_kind=model_kind,
        name=payload.name,
        slug=_slugify(payload.name),
        status="pending",
        replicas=payload.replicas,
        audit_payloads=payload.audit_payloads,
    )
    db.add(dep)
    await db.commit()
    await db.refresh(dep)
    await enqueue("deploy_model", dep.id)
    return _to_read(dep)


@router.get("", response_model=DeploymentList)
async def list_deployments(
    pagination: Pagination = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeploymentList:
    stmt = (
        scope_deployment_by_user(select(Deployment), user)
        .order_by(Deployment.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    count_stmt = scope_deployment_by_user(select(func.count(Deployment.id)), user)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return DeploymentList(items=[_to_read(r) for r in rows], total=total)


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeploymentRead:
    dep = await get_owned_deployment(db, deployment_id, user)
    return _to_read(dep)


@router.patch("/{deployment_id}", response_model=DeploymentRead)
async def update_deployment(
    deployment_id: str,
    payload: DeploymentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeploymentRead:
    dep = await get_owned_deployment(db, deployment_id, user)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name_must_not_be_empty")
        dep.name = name
    if payload.audit_payloads is not None:
        dep.audit_payloads = payload.audit_payloads
    await db.commit()
    await db.refresh(dep)
    return _to_read(dep)


@router.delete("/{deployment_id}", status_code=204, response_class=Response)
async def delete_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stop the serving container (best-effort) and remove the row."""
    dep = await get_owned_deployment(db, deployment_id, user)

    if dep.container_id:
        import structlog
        from httpx import HTTPError

        from aipacken.docker_client.builder_client import get_builder_client

        _log = structlog.get_logger(__name__)
        try:
            await get_builder_client().stop(dep.container_id, timeout=10)
        except (HTTPError, OSError) as exc:
            _log.warning(
                "deployment.delete.stop_failed",
                deployment_id=dep.id,
                container_id=dep.container_id,
                error=str(exc),
            )
            # Stale container may already be gone; don't block the delete on it.
            pass

    await db.delete(dep)
    await db.commit()
    return Response(status_code=204)


@router.get("/{deployment_id}/schema")
async def get_deployment_schema(
    deployment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the deployment's input schema.

    Prefers the live serving container's `/schema` when it's reachable,
    so any feature-name normalization it does shows up in the UI. Falls
    back to the trainer-produced `input_schema.json` on disk.
    """
    dep = await get_owned_deployment(db, deployment_id, user)

    if dep.status == "active" and dep.internal_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{dep.internal_url}/schema")
                if r.status_code == 200:
                    body = r.json()
                    return body.get("input") if isinstance(body, dict) and "input" in body else body
        except httpx.HTTPError:
            pass

    if dep.input_schema_json:
        return dep.input_schema_json

    run = await db.get(Run, dep.run_id)
    if run is not None:
        schema_path = storage.run_artifacts_dir(run.id) / "input_schema.json"
        if schema_path.exists():
            import json as _json

            try:
                return _json.loads(schema_path.read_text())
            except (OSError, _json.JSONDecodeError):
                # Malformed / missing schema file — fall through to the
                # empty-object default. Logged elsewhere by the trainer.
                pass

    return {"type": "object", "properties": {}, "additionalProperties": True}


@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: str,
    tail: int = 500,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Tail of the serving container's stdout/stderr, shaped for the UI."""
    import json as _json
    from datetime import datetime as _dt

    dep = await get_owned_deployment(db, deployment_id, user)
    if not dep.container_id:
        return []

    from aipacken.docker_client.builder_client import get_builder_client

    try:
        res = await get_builder_client().logs(dep.container_id, tail=tail)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"builder_unreachable: {exc}") from exc

    out: list[dict[str, str]] = []
    for raw in res.get("lines", []):
        raw = str(raw).strip()
        if not raw:
            continue
        if raw.startswith("{"):
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    out.append(
                        {
                            "ts": str(
                                parsed.get("ts")
                                or parsed.get("timestamp")
                                or _dt.now(UTC).isoformat()
                            ),
                            "level": str(parsed.get("level") or "info").lower(),
                            "message": str(parsed.get("message") or parsed.get("event") or raw),
                        }
                    )
                    continue
            except _json.JSONDecodeError:
                pass
        upper = raw.upper()
        level = "error" if "ERROR" in upper else ("warn" if "WARN" in upper else "info")
        out.append({"ts": _dt.now(UTC).isoformat(), "level": level, "message": raw})
    return out


@router.post(
    "/{deployment_id}/predict",
    response_model=PredictResponse,
    dependencies=[Depends(rate_limit(PREDICT_LIMIT))],
)
async def predict(
    deployment_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    dep = await get_owned_deployment(db, deployment_id, user)
    if dep.status != "active" or not dep.internal_url:
        raise HTTPException(status_code=409, detail="deployment_not_ready")

    # Accept either {inputs: {...}} or a flat {feature: value, ...} dict; the
    # serving container's schema-driven Pydantic model expects the flat form.
    forwarded: Any = payload.get("inputs") if "inputs" in payload else payload

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(f"{dep.internal_url}/predict", json=forwarded)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"serving_error: {exc}") from exc
        body = r.json()

    return PredictResponse(
        prediction=body.get("prediction"),
        prediction_label=body.get("prediction_label"),
        target_classes=body.get("target_classes"),
        model_version=body.get("model_version"),
        trace_id=body.get("trace_id"),
    )
