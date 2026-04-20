from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.experiments import (
    ExperimentCreate,
    ExperimentList,
    ExperimentRead,
    ExperimentUpdate,
)
from aipacken.db import get_db
from aipacken.db.models import Experiment, Run, User
from aipacken.jobs.tasks.train_run import cascade_delete_run_assets
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


@router.patch("/{experiment_id}", response_model=ExperimentRead)
async def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    exp = await db.get(Experiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name_must_not_be_empty")
        exp.name = name
    if payload.description is not None:
        exp.description = payload.description or None
    await db.commit()
    await db.refresh(exp)
    return exp


@router.delete("/{experiment_id}", status_code=204, response_class=Response)
async def delete_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    exp = await db.get(Experiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")

    # Cascade-delete every run (and its on-disk artifacts + model versions).
    run_ids = (
        await db.execute(select(Run.id).where(Run.experiment_id == experiment_id))
    ).scalars().all()
    for run_id in run_ids:
        await cascade_delete_run_assets(db, run_id)

    await db.delete(exp)
    await db.commit()
    return Response(status_code=204)
