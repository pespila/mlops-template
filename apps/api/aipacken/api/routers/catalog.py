from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.catalog import ModelCatalogEntryRead, ModelCatalogList
from aipacken.db import get_db
from aipacken.db.models import ModelCatalogEntry, User
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/models", response_model=ModelCatalogList)
async def list_catalog(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ModelCatalogList:
    rows = (
        (await db.execute(select(ModelCatalogEntry).order_by(ModelCatalogEntry.name)))
        .scalars()
        .all()
    )
    total = (await db.execute(select(func.count()).select_from(ModelCatalogEntry))).scalar_one()
    return ModelCatalogList(
        items=[ModelCatalogEntryRead.model_validate(r) for r in rows], total=total
    )
