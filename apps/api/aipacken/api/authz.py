"""Authorization helpers for resource ownership.

AIpacken resources trace back to a User. Direct ownership via ``user_id``:
Dataset, TransformConfig, Experiment. Derived ownership via parent chains:
Run → Experiment, Deployment → Run, ModelPackage → Run, Prediction →
Deployment.

Run telemetry (metrics, artifacts, explanations, bias reports) lives in
MLflow; authorization for those goes through ``get_owned_run`` — the
artifact download endpoint resolves the MLflow run's platform.run_id tag
and calls that helper.

MLflow ``RegisteredModel`` and its versions are a shared namespace — any
authenticated user can list / read them, mutations (promotion, delete)
remain admin-only, and per-version ownership is enforced by walking the
MLflow ``platform.run_id`` tag back to the DB Run → Experiment.user_id.

Admins (``user.role == "admin"``) bypass all filters. The seeded platform
admin is authoritative by design.

All "not found or not owned" paths raise 404 — never 403 — to avoid leaking
the existence of other users' resources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import (
    Dataset,
    Deployment,
    Experiment,
    ModelPackage,
    Run,
    TransformConfig,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

SelectT = TypeVar("SelectT", bound="Select[object]")


def is_admin(user: User) -> bool:
    return user.role == "admin"


def scope_by_user(stmt: SelectT, model_cls: type, user: User) -> SelectT:
    """Filter a select by ``model_cls.user_id`` unless the user is admin."""
    if is_admin(user):
        return stmt
    return stmt.where(model_cls.user_id == user.id)  # type: ignore[attr-defined]


def scope_run_by_user(stmt: SelectT, user: User) -> SelectT:
    if is_admin(user):
        return stmt
    return stmt.join(Experiment, Run.experiment_id == Experiment.id).where(
        Experiment.user_id == user.id
    )


def scope_deployment_by_user(stmt: SelectT, user: User) -> SelectT:
    """Filter a Deployment-bound select via Run → Experiment."""
    if is_admin(user):
        return stmt
    return (
        stmt.join(Run, Deployment.run_id == Run.id)
        .join(Experiment, Run.experiment_id == Experiment.id)
        .where(Experiment.user_id == user.id)
    )


def scope_package_by_user(stmt: SelectT, user: User) -> SelectT:
    if is_admin(user):
        return stmt
    return (
        stmt.join(Run, ModelPackage.run_id == Run.id)
        .join(Experiment, Run.experiment_id == Experiment.id)
        .where(Experiment.user_id == user.id)
    )


async def get_owned_dataset(
    db: AsyncSession, dataset_id: str, user: User, *, detail: str = "dataset_not_found"
) -> Dataset:
    d = await db.get(Dataset, dataset_id)
    if d is None or (not is_admin(user) and d.user_id != user.id):
        raise HTTPException(status_code=404, detail=detail)
    return d


async def get_owned_experiment(
    db: AsyncSession, experiment_id: str, user: User, *, detail: str = "experiment_not_found"
) -> Experiment:
    exp = await db.get(Experiment, experiment_id)
    if exp is None or (not is_admin(user) and exp.user_id != user.id):
        raise HTTPException(status_code=404, detail=detail)
    return exp


async def get_owned_transform_config(
    db: AsyncSession,
    tc_id: str,
    user: User,
    *,
    detail: str = "transform_config_not_found",
) -> TransformConfig:
    tc = await db.get(TransformConfig, tc_id)
    if tc is None or (not is_admin(user) and tc.user_id != user.id):
        raise HTTPException(status_code=404, detail=detail)
    return tc


async def _run_owner_id(db: AsyncSession, run: Run) -> str | None:
    exp = await db.get(Experiment, run.experiment_id)
    return exp.user_id if exp is not None else None


async def get_owned_run(
    db: AsyncSession, run_id: str, user: User, *, detail: str = "run_not_found"
) -> Run:
    r = await db.get(Run, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=detail)
    if is_admin(user):
        return r
    if await _run_owner_id(db, r) != user.id:
        raise HTTPException(status_code=404, detail=detail)
    return r


async def get_owned_deployment(
    db: AsyncSession, deployment_id: str, user: User, *, detail: str = "deployment_not_found"
) -> Deployment:
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail=detail)
    if is_admin(user):
        return dep
    run = await db.get(Run, dep.run_id)
    if run is None or await _run_owner_id(db, run) != user.id:
        raise HTTPException(status_code=404, detail=detail)
    return dep


async def get_owned_package(
    db: AsyncSession, pkg_id: str, user: User, *, detail: str = "package_not_found"
) -> ModelPackage:
    pkg = await db.get(ModelPackage, pkg_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail=detail)
    if is_admin(user):
        return pkg
    run = await db.get(Run, pkg.run_id)
    if run is None or await _run_owner_id(db, run) != user.id:
        raise HTTPException(status_code=404, detail=detail)
    return pkg
