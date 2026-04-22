from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.authz import get_owned_dataset, scope_by_user
from aipacken.api.schemas.datasets import (
    DatasetList,
    DatasetPatch,
    DatasetProfile,
    DatasetRead,
    FeatureSchemaPatch,
    FeatureSchemaRead,
)
from aipacken.db import get_db
from aipacken.db.models import Dataset, FeatureSchema, Run, User
from aipacken.jobs.queue import enqueue
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetRead, status_code=201)
async def create_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    dataset_id = str(uuid.uuid4())
    filename = file.filename or dataset_id
    dest = storage.dataset_raw_path(dataset_id, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256()
    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            size += len(chunk)

    display_name = name or filename.rsplit(".", 1)[0]

    dataset = Dataset(
        id=dataset_id,
        user_id=user.id,
        name=display_name,
        source_filename=file.filename,
        size_bytes=size,
        storage_path=storage.to_relative(dest),
        checksum=h.hexdigest(),
        status="uploaded",
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    await enqueue("profile_dataset", dataset.id)
    return dataset


@router.get("", response_model=DatasetList)
async def list_datasets(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DatasetList:
    stmt = scope_by_user(select(Dataset), Dataset, user).order_by(Dataset.created_at.desc())
    count_stmt = scope_by_user(select(func.count()).select_from(Dataset), Dataset, user)
    items = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return DatasetList(items=[DatasetRead.model_validate(d) for d in items], total=total)


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    return await get_owned_dataset(db, dataset_id, user)


@router.get("/{dataset_id}/profile", response_model=DatasetProfile)
async def get_dataset_profile(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetProfile:
    d = await get_owned_dataset(db, dataset_id, user)
    return DatasetProfile(
        dataset_id=d.id, summary=d.profile_summary_json, report_path=d.profile_path
    )


@router.get("/{dataset_id}/schema", response_model=list[FeatureSchemaRead])
async def get_dataset_schema(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeatureSchemaRead]:
    await get_owned_dataset(db, dataset_id, user)
    rows = (
        (await db.execute(select(FeatureSchema).where(FeatureSchema.dataset_id == dataset_id)))
        .scalars()
        .all()
    )
    return [FeatureSchemaRead.from_row(r) for r in rows]


@router.patch("/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: str,
    payload: DatasetPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    d = await get_owned_dataset(db, dataset_id, user)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name_must_not_be_empty")
        d.name = name
    await db.commit()
    await db.refresh(d)
    return d


@router.delete("/{dataset_id}", status_code=204, response_class=Response)
async def delete_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    d = await get_owned_dataset(db, dataset_id, user)

    # Refuse if any run still references this dataset — user must clear
    # dependent experiments/runs first. Blocker count is kept global on
    # purpose: a dataset with runs from any user is not safe to delete.
    run_count = (
        await db.execute(select(func.count()).select_from(Run).where(Run.dataset_id == dataset_id))
    ).scalar_one()
    if run_count:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "runs_exist",
                "message": (
                    f"{run_count} run(s) still reference this dataset. "
                    "Delete the experiments/runs first."
                ),
            },
        )

    raw = storage.to_absolute(d.storage_path) if d.storage_path else None
    profile = storage.to_absolute(d.profile_path) if d.profile_path else None

    await db.delete(d)
    await db.commit()

    for path in (raw, profile):
        if path is None:
            continue
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                import shutil

                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    return Response(status_code=204)


@router.patch(
    "/{dataset_id}/schema/{column_name}",
    response_model=FeatureSchemaRead,
)
async def patch_column_type(
    dataset_id: str,
    column_name: str,
    payload: FeatureSchemaPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureSchemaRead:
    await get_owned_dataset(db, dataset_id, user)
    row = (
        await db.execute(
            select(FeatureSchema).where(
                FeatureSchema.dataset_id == dataset_id,
                FeatureSchema.column_name == column_name,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="column_not_found")
    row.semantic_type = payload.semantic_type
    await db.commit()
    await db.refresh(row)

    # Re-run profiling so stats reflect the new type interpretation
    # (parsed datetimes, coerced numerics, …). The worker keeps all
    # non-NULL semantic_type values intact.
    await enqueue("profile_dataset", dataset_id, preserve_user_types=True)

    return FeatureSchemaRead.from_row(row)
