from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.schemas.runs import (
    ArtifactRead,
    MetricRead,
    RunCreate,
    RunList,
    RunRead,
    RunUpdate,
)
from aipacken.db import get_db
from aipacken.db.models import (
    Artifact,
    BiasReport,
    Deployment,
    ExplanationArtifact,
    Metric,
    ModelVersion,
    Run,
    TransformConfig,
    User,
)
from aipacken.jobs.queue import enqueue
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=201)
async def create_run(
    payload: RunCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    transform_config_id = payload.transform_config_id
    if transform_config_id is None:
        if payload.transform_config is None:
            raise HTTPException(
                status_code=422,
                detail="either transform_config_id or transform_config must be provided",
            )
        sens = payload.transform_config.get("sensitive_features") or []
        tc = TransformConfig(
            dataset_id=payload.dataset_id,
            user_id=user.id,
            target_column=str(payload.transform_config.get("target", "")),
            transforms_json=payload.transform_config.get("transforms") or [],
            split_json=payload.transform_config.get("split") or {},
            sensitive_features=[str(c) for c in sens] if isinstance(sens, list) else [],
        )
        db.add(tc)
        await db.flush()
        transform_config_id = tc.id

    run = Run(
        experiment_id=payload.experiment_id,
        dataset_id=payload.dataset_id,
        transform_config_id=transform_config_id,
        model_catalog_id=payload.model_catalog_id,
        hyperparams_json=payload.hyperparams,
        resource_limits_json=payload.resource_limits,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await enqueue("train_run", run.id)
    return run


@router.get("", response_model=RunList)
async def list_runs(
    experiment_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunList:
    stmt = select(Run).order_by(Run.created_at.desc())
    count_stmt = select(func.count()).select_from(Run)
    if experiment_id:
        stmt = stmt.where(Run.experiment_id == experiment_id)
        count_stmt = count_stmt.where(Run.experiment_id == experiment_id)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return RunList(items=[RunRead.model_validate(r) for r in rows], total=total)


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    r = await db.get(Run, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return r


@router.get("/{run_id}/metrics", response_model=list[MetricRead])
async def get_run_metrics(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Metric]:
    rows = (
        await db.execute(select(Metric).where(Metric.run_id == run_id).order_by(Metric.step))
    ).scalars().all()
    return list(rows)


@router.get("/{run_id}/artifacts", response_model=list[ArtifactRead])
async def get_run_artifacts(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ArtifactRead]:
    rows = (
        await db.execute(select(Artifact).where(Artifact.run_id == run_id))
    ).scalars().all()
    return [ArtifactRead.from_row(r) for r in rows]


@router.get("/{run_id}/explanations")
async def get_run_explanations(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    rows = (
        await db.execute(
            select(ExplanationArtifact).where(ExplanationArtifact.run_id == run_id)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "feature_importance": r.feature_importance_json or {},
            "artifact_path": r.artifact_path,
        }
        for r in rows
    ]


@router.get("/{run_id}/bias")
async def get_run_bias(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    rows = (
        await db.execute(select(BiasReport).where(BiasReport.run_id == run_id))
    ).scalars().all()
    return [
        {
            "id": r.id,
            "sensitive_feature": r.sensitive_feature,
            "metric_name": r.metric_name,
            "overall_value": r.overall_value,
            "group_values": r.group_values_json or {},
        }
        for r in rows
    ]


@router.get("/{run_id}/selected_hyperparams")
async def get_run_selected_hyperparams(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Return the parsed ``selected_hyperparams.json`` artifact for a run.

    Falls back to the raw ``Run.hyperparams_json`` (labelled ``source=legacy``)
    for runs trained before this artifact was introduced so the Model tab on
    older runs still renders a useful payload.
    """
    import json

    row = (
        await db.execute(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.kind == "selected_hyperparams",
            )
        )
    ).scalars().first()
    if row is not None:
        try:
            abs_path = storage.to_absolute(row.uri)
            if abs_path.exists():
                return json.loads(abs_path.read_text())
        except Exception:  # noqa: BLE001
            pass
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "source": "legacy",
        "model_name": None,
        "task": None,
        "hyperparameters": run.hyperparams_json or {},
    }


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Replay the persisted training-log transcript for a run.

    Returns one record per captured line in the shape the frontend's
    TrainingLogStream already consumes. When the trainer is still running
    the file may be missing or partial — the SSE channel fills the gap.
    """
    r = await db.get(Run, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="run_not_found")

    logs_path = storage.run_logs_path(run_id)
    if not logs_path.exists():
        return []

    from datetime import datetime as _dt, timezone as _tz
    import json as _json

    out: list[dict[str, str]] = []
    for raw in logs_path.read_text(errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("{"):
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    out.append(
                        {
                            "ts": str(parsed.get("ts") or _dt.now(_tz.utc).isoformat()),
                            "level": str(parsed.get("level") or "info").lower(),
                            "message": str(parsed.get("message") or parsed.get("msg") or raw),
                        }
                    )
                    continue
            except _json.JSONDecodeError:
                pass
        upper = raw.upper()
        level = "error" if "ERROR" in upper else ("warn" if "WARN" in upper else "info")
        out.append({"ts": _dt.now(_tz.utc).isoformat(), "level": level, "message": raw})
    return out


@router.patch("/{run_id}", response_model=RunRead)
async def update_run(
    run_id: str,
    payload: RunUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    r = await db.get(Run, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    if payload.display_name is not None:
        r.display_name = payload.display_name.strip() or None
    await db.commit()
    await db.refresh(r)
    return r


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    r = await db.get(Run, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    r.status = "cancelling"
    await db.commit()
    await db.refresh(r)
    return r


@router.delete("/{run_id}", status_code=204, response_class=Response)
async def delete_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from aipacken.jobs.tasks.train_run import cascade_delete_run_assets

    # Block the delete if any model version produced by this run is still
    # referenced by a Deployment. User must remove the deployments first.
    blockers = (
        await db.execute(
            select(Deployment.id, Deployment.name, Deployment.slug, Deployment.status)
            .join(ModelVersion, Deployment.model_version_id == ModelVersion.id)
            .where(ModelVersion.run_id == run_id)
        )
    ).all()
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "deployments_exist",
                "message": (
                    f"{len(blockers)} deployment(s) still reference models from this "
                    "run. Delete the deployments first."
                ),
                "deployments": [
                    {"id": b.id, "name": b.name, "slug": b.slug, "status": b.status}
                    for b in blockers
                ],
            },
        )

    await cascade_delete_run_assets(db, run_id)
    await db.commit()
    return Response(status_code=204)
