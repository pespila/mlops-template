"""Model registry router — reads straight from MLflow.

After Batch 35b the DB no longer stores RegisteredModel / ModelVersion
rows; MLflow's built-in registry is the source of truth. This router
projects MLflow's registered models + versions into the same Pydantic
shapes the frontend already consumes, and promotions become alias writes
(``@staging`` / ``@production``) on the MLflow side.

The ``id`` field on ``ModelVersionRead`` is synthesized as
``{name}:{version}`` so the frontend can route /models/{name}/versions/{id}
without depending on MLflow's internal primary key.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.pagination import Pagination, pagination_params
from aipacken.api.schemas.models import (
    ModelUpdate,
    ModelVersionPromote,
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
    ModelCatalogEntry,
    Run,
    User,
)
from aipacken.services import mlflow_client
from aipacken.services.auth import get_current_user, require_admin

router = APIRouter(prefix="/models", tags=["models"])


def _ms_to_dt(ms: int | None) -> datetime:
    if not ms:
        return datetime.now(UTC)
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _registered_model_to_read(rm) -> RegisteredModelRead:
    desc = getattr(rm, "description", None) or None
    return RegisteredModelRead(
        id=rm.name,
        name=rm.name,
        description=desc,
        created_at=_ms_to_dt(getattr(rm, "creation_timestamp", None)),
        updated_at=_ms_to_dt(
            getattr(rm, "last_updated_timestamp", None) or getattr(rm, "creation_timestamp", None)
        ),
    )


def _alias_to_stage(aliases: list[str]) -> str:
    if "production" in aliases:
        return "production"
    if "staging" in aliases:
        return "staging"
    if "archived" in aliases:
        return "archived"
    return "none"


async def _enrich_mlflow_version(db: AsyncSession, mv, registered_name: str) -> ModelVersionRead:
    """Shape an MLflow ModelVersion + adjacent DB metadata into a read model."""
    tags = dict(getattr(mv, "tags", None) or {})
    platform_run_id = tags.get("platform.run_id") or ""

    # Pull metrics from the run's data (live — aliases should follow).
    metrics_map: dict[str, float] = {}
    if platform_run_id:
        rows = mlflow_client.get_run_metrics(platform_run_id)
        latest: dict[str, float] = {}
        for r in rows:
            latest[r["name"]] = float(r["value"])
        metrics_map = latest

    dataset_id: str | None = None
    dataset_name: str | None = None
    experiment_id: str | None = None
    model_catalog_name: str | None = None
    model_kind = tags.get("platform.model_kind") or "sklearn"
    if platform_run_id:
        run = await db.get(Run, platform_run_id)
        if run is not None:
            experiment_id = run.experiment_id
            ds = await db.get(Dataset, run.dataset_id)
            if ds is not None:
                dataset_id = ds.id
                dataset_name = ds.name
            entry = await db.get(ModelCatalogEntry, run.model_catalog_id)
            if entry is not None:
                model_catalog_name = entry.name

    aliases = mlflow_client.aliases_for_version(registered_name, mv.version)

    return ModelVersionRead(
        id=f"{registered_name}:{mv.version}",
        registered_model_name=registered_name,
        registered_model_id=registered_name,
        version=int(mv.version),
        stage=_alias_to_stage(aliases),
        aliases=aliases,
        run_id=platform_run_id,
        mlflow_run_id=getattr(mv, "run_id", "") or "",
        model_kind=model_kind,
        storage_path=None,
        input_schema_json={},
        output_schema_json={},
        serving_image_uri=tags.get("platform.serving_image_uri") or None,
        created_at=_ms_to_dt(getattr(mv, "creation_timestamp", None)),
        updated_at=_ms_to_dt(
            getattr(mv, "last_updated_timestamp", None) or getattr(mv, "creation_timestamp", None)
        ),
        metrics=metrics_map,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        experiment_id=experiment_id,
        model_catalog_name=model_catalog_name,
    )


def _user_owns_version(mv, user: User, user_experiment_ids: set[str]) -> bool:
    """True if *user* owns the platform Run that produced *mv*."""
    if user.role == "admin":
        return True
    tags = dict(getattr(mv, "tags", None) or {})
    exp = tags.get("platform.experiment_id") or ""
    return exp in user_experiment_ids


async def _user_experiment_ids(db: AsyncSession, user: User) -> set[str]:
    if user.role == "admin":
        return set()
    rows = (
        (await db.execute(select(Experiment.id).where(Experiment.user_id == user.id)))
        .scalars()
        .all()
    )
    return set(rows)


@router.get("", response_model=RegisteredModelList)
async def list_models(
    pagination: Pagination = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModelList:
    all_rms = mlflow_client.list_registered_models()
    # Sort for stable pagination (MLflow returns no deterministic order).
    all_rms.sort(key=lambda r: r.name)
    total = len(all_rms)
    page = all_rms[pagination.offset : pagination.offset + pagination.limit]
    return RegisteredModelList(items=[_registered_model_to_read(r) for r in page], total=total)


@router.get("/{model_id}", response_model=RegisteredModelDetail)
async def get_model(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModelDetail:
    # ``model_id`` here IS the MLflow registered-model name (see list_models);
    # we kept the URL shape so the frontend didn't need rewiring.
    rm = mlflow_client.get_registered_model(model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    owner_exps = await _user_experiment_ids(db, user)
    mvs = mlflow_client.search_model_versions(model_id)
    visible = [mv for mv in mvs if _user_owns_version(mv, user, owner_exps)]
    versions = [await _enrich_mlflow_version(db, mv, model_id) for mv in visible]

    base = _registered_model_to_read(rm)
    return RegisteredModelDetail(
        id=base.id,
        name=base.name,
        description=base.description,
        created_at=base.created_at,
        updated_at=base.updated_at,
        versions=versions,
    )


@router.patch("/{model_id}", response_model=RegisteredModelRead)
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RegisteredModelRead:
    """Update the MLflow RegisteredModel name / description (admin only).

    Renaming walks Deployment.registered_model_name and
    ModelPackage.registered_model_name to the new name in the same
    commit so snapshots keep pointing at the right MLflow entity.
    """
    rm = mlflow_client.get_registered_model(model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    client = mlflow_client.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="mlflow_unavailable")

    current_name = model_id
    if payload.name is not None and payload.name.strip() and payload.name.strip() != current_name:
        new_name = payload.name.strip()
        try:
            client.rename_registered_model(name=current_name, new_name=new_name)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"mlflow_rename_failed:{exc}") from exc
        await db.execute(
            Deployment.__table__.update()
            .where(Deployment.registered_model_name == current_name)
            .values(registered_model_name=new_name)
        )
        from aipacken.db.models import ModelPackage as _Pkg

        await db.execute(
            _Pkg.__table__.update()
            .where(_Pkg.registered_model_name == current_name)
            .values(registered_model_name=new_name)
        )
        await db.commit()
        current_name = new_name

    if payload.description is not None:
        try:
            client.update_registered_model(name=current_name, description=payload.description or "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"mlflow_update_failed:{exc}") from exc

    rm_after = mlflow_client.get_registered_model(current_name)
    return _registered_model_to_read(rm_after)


@router.delete("/{model_id}", status_code=204, response_class=Response)
async def delete_model(
    model_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete an MLflow RegisteredModel + every version under it.

    Fails with 409 if any Deployment still references a version of this
    model — the caller must tear those down first.
    """
    rm = mlflow_client.get_registered_model(model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    blockers = (
        await db.execute(
            select(Deployment.id, Deployment.name, Deployment.slug, Deployment.status).where(
                Deployment.registered_model_name == model_id
            )
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

    client = mlflow_client.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="mlflow_unavailable")
    try:
        client.delete_registered_model(name=model_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"mlflow_delete_failed:{exc}") from exc
    return Response(status_code=204)


@router.post(
    "/{model_id}/versions/{version_id}/promote",
    response_model=ModelVersionRead,
)
async def promote_version(
    model_id: str,
    version_id: str,
    payload: ModelVersionPromote,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ModelVersionRead:
    """Promote an MLflow ModelVersion via alias writes.

    ``version_id`` is ``{name}:{version}`` — we accept both that shape
    and a bare version number. Target ``production`` sets ``@production``
    (MLflow alias uniqueness auto-moves it off the previous version).
    ``staging`` sets ``@staging``. ``archived`` / ``none`` clear both.
    """
    rm = mlflow_client.get_registered_model(model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")

    if ":" in version_id:
        _, _, version_num = version_id.partition(":")
    else:
        version_num = version_id
    if not version_num.isdigit():
        raise HTTPException(status_code=422, detail="invalid_version_id")

    mv = mlflow_client.get_model_version(model_id, version_num)
    if mv is None:
        raise HTTPException(status_code=404, detail="version_not_found")

    target = payload.stage
    if target == "production":
        mlflow_client.set_alias(model_id, "production", version_num)
    elif target == "staging":
        mlflow_client.set_alias(model_id, "staging", version_num)
    elif target == "archived":
        # Aliases present on this specific version are what we clear —
        # other versions keep theirs.
        for alias in mlflow_client.aliases_for_version(model_id, version_num):
            mlflow_client.delete_alias(model_id, alias)
        mlflow_client.set_alias(model_id, "archived", version_num)
    else:  # "none"
        for alias in mlflow_client.aliases_for_version(model_id, version_num):
            mlflow_client.delete_alias(model_id, alias)

    mv_after = mlflow_client.get_model_version(model_id, version_num)
    return await _enrich_mlflow_version(db, mv_after, model_id)


@router.get("/{model_id}/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelVersionRead]:
    owner_exps = await _user_experiment_ids(db, user)
    mvs = mlflow_client.search_model_versions(model_id)
    visible = [mv for mv in mvs if _user_owns_version(mv, user, owner_exps)]
    return [await _enrich_mlflow_version(db, mv, model_id) for mv in visible]
