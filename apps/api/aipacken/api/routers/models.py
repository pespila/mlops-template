from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aipacken.api.schemas.models import (
    ModelVersionRead,
    RegisteredModelDetail,
    RegisteredModelList,
    RegisteredModelRead,
)
from aipacken.db import get_db
from aipacken.db.models import ModelVersion, RegisteredModel, User
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/models", tags=["models"])


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
    return RegisteredModelDetail(
        id=rm.id,
        name=rm.name,
        description=rm.description,
        mlflow_name=rm.mlflow_name,
        created_at=rm.created_at,
        updated_at=rm.updated_at,
        versions=[ModelVersionRead.model_validate(v) for v in rm.versions],
    )


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelVersion]:
    rows = (
        await db.execute(
            select(ModelVersion)
            .where(ModelVersion.registered_model_id == model_id)
            .order_by(ModelVersion.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
