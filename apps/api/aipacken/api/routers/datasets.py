from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.schemas.datasets import (
    DatasetList,
    DatasetProfile,
    DatasetRead,
    FeatureSchemaRead,
)
from aipacken.db import get_db
from aipacken.db.models import Dataset, FeatureSchema, User
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
    items = (await db.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().all()
    total = (await db.execute(select(func.count()).select_from(Dataset))).scalar_one()
    return DatasetList(items=[DatasetRead.model_validate(d) for d in items], total=total)


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    d = await db.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset_not_found")
    return d


@router.get("/{dataset_id}/profile", response_model=DatasetProfile)
async def get_dataset_profile(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetProfile:
    d = await db.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset_not_found")
    return DatasetProfile(
        dataset_id=d.id, summary=d.profile_summary_json, report_path=d.profile_path
    )


@router.get("/{dataset_id}/schema", response_model=list[FeatureSchemaRead])
async def get_dataset_schema(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeatureSchemaRead]:
    d = await db.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset_not_found")
    rows = (
        await db.execute(select(FeatureSchema).where(FeatureSchema.dataset_id == dataset_id))
    ).scalars().all()
    return [FeatureSchemaRead.from_row(r) for r in rows]
