from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.runs import (
    ArtifactRead,
    MetricRead,
    RunCreate,
    RunList,
    RunRead,
)
from aipacken.db import get_db
from aipacken.db.models import Artifact, Metric, Run, TransformConfig, User
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
        tc = TransformConfig(
            dataset_id=payload.dataset_id,
            user_id=user.id,
            target_column=str(payload.transform_config.get("target", "")),
            transforms_json=payload.transform_config.get("transforms") or [],
            split_json=payload.transform_config.get("split") or {},
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
) -> list[Artifact]:
    rows = (
        await db.execute(select(Artifact).where(Artifact.run_id == run_id))
    ).scalars().all()
    return list(rows)


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
