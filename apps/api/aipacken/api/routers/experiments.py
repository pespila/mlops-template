from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.experiments import ExperimentCreate, ExperimentList, ExperimentRead
from aipacken.db import get_db
from aipacken.db.models import Experiment, User
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentRead, status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    exp = Experiment(user_id=user.id, name=payload.name, description=payload.description)
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


@router.get("", response_model=ExperimentList)
async def list_experiments(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ExperimentList:
    rows = (
        await db.execute(select(Experiment).order_by(Experiment.created_at.desc()))
    ).scalars().all()
    total = (await db.execute(select(func.count()).select_from(Experiment))).scalar_one()
    return ExperimentList(items=[ExperimentRead.model_validate(r) for r in rows], total=total)


@router.get("/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    exp = await db.get(Experiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return exp
