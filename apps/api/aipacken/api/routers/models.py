from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aipacken.api.schemas.models import (
    ModelUpdate,
    ModelVersionRead,
    RegisteredModelDetail,
    RegisteredModelList,
    RegisteredModelRead,
)
from aipacken.db import get_db
from aipacken.db.models import (
    Dataset,
    Metric,
    ModelCatalogEntry,
    ModelVersion,
    RegisteredModel,
    Run,
    User,
)
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/models", tags=["models"])


async def _enrich_version(db: AsyncSession, v: ModelVersion) -> ModelVersionRead:
    """Fold metrics + dataset + catalog name onto a ModelVersionRead."""
    mv = ModelVersionRead.model_validate(v)
    run = await db.get(Run, v.run_id)
    if run is not None:
        mv.experiment_id = run.experiment_id
        dataset = await db.get(Dataset, run.dataset_id)
        if dataset is not None:
            mv.dataset_id = dataset.id
            mv.dataset_name = dataset.name
        entry = await db.get(ModelCatalogEntry, run.model_catalog_id)
        if entry is not None:
            mv.model_catalog_name = entry.name

    metric_rows = (
        await db.execute(select(Metric).where(Metric.run_id == v.run_id))
    ).scalars().all()
    mv.metrics = {m.name: float(m.value) for m in metric_rows}
    return mv


@router.get("", response_model=RegisteredModelList)
async def list_models(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> RegisteredModelList:
    rows = (
        await db.execute(select(RegisteredModel).order_by(RegisteredModel.name))
    ).scalars().all()
    total = (await db.execute(select(func.count()).select_from(RegisteredModel))).scalar_one()
    return RegisteredModelList(
        items=[RegisteredModelRead.model_validate(r) for r in rows], total=total
    )


@router.get("/{model_id}", response_model=RegisteredModelDetail)
async def get_model(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModelDetail:
    rm = (
        await db.execute(
            select(RegisteredModel)
            .options(selectinload(RegisteredModel.versions))
            .where(RegisteredModel.id == model_id)
        )
    ).scalar_one_or_none()
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")
    versions = [await _enrich_version(db, v) for v in rm.versions]
    return RegisteredModelDetail(
        id=rm.id,
        name=rm.name,
        description=rm.description,
        created_at=rm.created_at,
        updated_at=rm.updated_at,
        versions=versions,
    )


@router.patch("/{model_id}", response_model=RegisteredModelRead)
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModel:
    rm = await db.get(RegisteredModel, model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name_must_not_be_empty")
        rm.name = name
    if payload.description is not None:
        rm.description = payload.description or None
    await db.commit()
    await db.refresh(rm)
    return rm


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelVersionRead]:
    rows = (
        await db.execute(
            select(ModelVersion)
            .where(ModelVersion.registered_model_id == model_id)
            .order_by(ModelVersion.created_at.desc())
        )
    ).scalars().all()
    return [await _enrich_version(db, v) for v in rows]
