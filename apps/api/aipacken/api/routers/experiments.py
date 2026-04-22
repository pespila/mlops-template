from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.authz import get_owned_experiment, scope_by_user
from aipacken.api.schemas.experiments import (
    ExperimentCreate,
    ExperimentList,
    ExperimentRead,
    ExperimentUpdate,
)
from aipacken.db import get_db
from aipacken.db.models import Deployment, Experiment, ModelVersion, Run, User
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
    stmt = scope_by_user(select(Experiment), Experiment, user).order_by(
        Experiment.created_at.desc()
    )
    count_stmt = scope_by_user(select(func.count()).select_from(Experiment), Experiment, user)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return ExperimentList(items=[ExperimentRead.model_validate(r) for r in rows], total=total)


@router.get("/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    return await get_owned_experiment(db, experiment_id, user)


@router.patch("/{experiment_id}", response_model=ExperimentRead)
async def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    exp = await get_owned_experiment(db, experiment_id, user)
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
    exp = await get_owned_experiment(db, experiment_id, user)

    # Refuse the delete if any model version produced by a run in this
    # experiment still has a Deployment — user must remove those first.
    blockers = (
        await db.execute(
            select(Deployment.id, Deployment.name, Deployment.slug, Deployment.status)
            .join(ModelVersion, Deployment.model_version_id == ModelVersion.id)
            .join(Run, ModelVersion.run_id == Run.id)
            .where(Run.experiment_id == experiment_id)
        )
    ).all()
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "deployments_exist",
                "message": (
                    f"{len(blockers)} deployment(s) still reference models from this "
                    "experiment. Delete the deployments first."
                ),
                "deployments": [
                    {"id": b.id, "name": b.name, "slug": b.slug, "status": b.status}
                    for b in blockers
                ],
            },
        )

    # Cascade-delete every run (and its on-disk artifacts + model versions).
    run_ids = (
        await db.execute(select(Run.id).where(Run.experiment_id == experiment_id))
    ).scalars().all()
    for run_id in run_ids:
        await cascade_delete_run_assets(db, run_id)

    await db.delete(exp)
    await db.commit()
    return Response(status_code=204)
