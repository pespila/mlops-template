from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.authz import is_admin
from aipacken.api.pagination import Pagination, pagination_params
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
    Deployment,
    Experiment,
    Metric,
    ModelCatalogEntry,
    ModelVersion,
    RegisteredModel,
    Run,
    User,
)
from aipacken.services.auth import get_current_user, require_admin

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
        (await db.execute(select(Metric).where(Metric.run_id == v.run_id))).scalars().all()
    )
    mv.metrics = {m.name: float(m.value) for m in metric_rows}
    return mv


@router.get("", response_model=RegisteredModelList)
async def list_models(
    pagination: Pagination = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModelList:
    rows = (
        (
            await db.execute(
                select(RegisteredModel)
                .order_by(RegisteredModel.name)
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
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
    rm = await db.get(RegisteredModel, model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    # RegisteredModel is a shared namespace, but versions are owner-scoped:
    # filter `versions` down to those whose source Run sits in an Experiment
    # owned by the current user (admins see everything).
    stmt = select(ModelVersion).where(ModelVersion.registered_model_id == model_id)
    if not is_admin(user):
        stmt = (
            stmt.join(Run, ModelVersion.run_id == Run.id)
            .join(Experiment, Run.experiment_id == Experiment.id)
            .where(Experiment.user_id == user.id)
        )
    version_rows = (await db.execute(stmt)).scalars().all()
    versions = [await _enrich_version(db, v) for v in version_rows]
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
    # RegisteredModel is a shared resource; only admins mutate its metadata.
    user: User = Depends(require_admin),
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


@router.delete("/{model_id}", status_code=204, response_class=Response)
async def delete_model(
    model_id: str,
    # Deleting a shared RegisteredModel wipes versions created by multiple
    # users. Admin-only until the model schema gains tenant ownership.
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a registered model and every version under it.

    Fails with 409 if any version is still referenced by a Deployment — the
    caller must tear those down first. On success the on-disk version
    directories are removed alongside the DB rows.
    """
    rm = await db.get(RegisteredModel, model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    blockers = (
        await db.execute(
            select(Deployment.id, Deployment.name, Deployment.slug, Deployment.status)
            .join(ModelVersion, Deployment.model_version_id == ModelVersion.id)
            .where(ModelVersion.registered_model_id == model_id)
        )
    ).all()
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "deployments_exist",
                "message": (
                    f"{len(blockers)} deployment(s) still reference versions of this "
                    "model. Delete the deployments first."
                ),
                "deployments": [
                    {"id": b.id, "name": b.name, "slug": b.slug, "status": b.status}
                    for b in blockers
                ],
            },
        )

    version_ids = (
        (
            await db.execute(
                select(ModelVersion.id).where(ModelVersion.registered_model_id == model_id)
            )
        )
        .scalars()
        .all()
    )
    for mv_id in version_ids:
        mv_dir = storage.model_version_dir(mv_id)
        if mv_dir.exists():
            shutil.rmtree(mv_dir, ignore_errors=True)

    # RegisteredModel.versions has cascade="all, delete-orphan" so deleting
    # the parent removes the ModelVersion rows in one shot.
    await db.delete(rm)
    await db.commit()
    return Response(status_code=204)


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelVersionRead]:
    stmt = (
        select(ModelVersion)
        .where(ModelVersion.registered_model_id == model_id)
        .order_by(ModelVersion.created_at.desc())
    )
    if not is_admin(user):
        stmt = (
            stmt.join(Run, ModelVersion.run_id == Run.id)
            .join(Experiment, Run.experiment_id == Experiment.id)
            .where(Experiment.user_id == user.id)
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_version(db, v) for v in rows]
