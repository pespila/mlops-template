from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.predictions import PredictionList, PredictionRead
from aipacken.db import get_db
from aipacken.db.models import Prediction, User
from aipacken.services.auth import get_current_user

router = APIRouter(tags=["predictions"])


@router.get("/deployments/{deployment_id}/predictions", response_model=PredictionList)
async def list_predictions(
    deployment_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PredictionList:
    offset = (page - 1) * page_size
    stmt = (
        select(Prediction)
        .where(Prediction.deployment_id == deployment_id)
        .order_by(Prediction.received_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    total = (
        await db.execute(
            select(func.count())
            .select_from(Prediction)
            .where(Prediction.deployment_id == deployment_id)
        )
    ).scalar_one()
    return PredictionList(
        items=[PredictionRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
