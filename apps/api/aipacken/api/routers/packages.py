"""Downloadable deployment packages for MLflow model versions.

Packages are built asynchronously by the ``build_package`` worker job
and streamed back on demand. Each package is tied to a platform Run
(authorization anchor) plus a snapshotted MLflow ModelVersion that
identifies which registered-model artifact to bundle.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.authz import (
    get_owned_package,
    get_owned_run,
    scope_package_by_user,
)
from aipacken.db import get_db
from aipacken.db.models import ModelPackage, User
from aipacken.jobs.queue import enqueue
from aipacken.services import mlflow_client
from aipacken.services.auth import get_current_user

router = APIRouter(tags=["packages"])


class ModelPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    run_id: str
    registered_model_name: str | None = None
    version_number: int | None = None
    mlflow_run_id: str | None = None
    model_kind: str = "sklearn"
    status: str
    storage_path: str | None = None
    size_bytes: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


@router.post(
    "/runs/{run_id}/package",
    response_model=ModelPackageRead,
    status_code=201,
)
async def create_package(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelPackage:
    """Kick off a package build for the MLflow version produced by ``run_id``.

    Re-triggering always creates a fresh row — older packages stay on
    disk until the cleanup job prunes them, so the user can still
    download in-flight builds while a newer one assembles.
    """
    run = await get_owned_run(db, run_id, user)

    mlflow_run = mlflow_client.find_run_by_platform_id(run.id)
    if mlflow_run is None:
        raise HTTPException(status_code=404, detail="mlflow_run_not_found")

    tags = dict(mlflow_run.data.tags or {})
    model_kind = tags.get("platform.model_kind") or "sklearn"

    registered_name: str | None = None
    version_number: int | None = None
    registered_name_tag = tags.get("platform.registered_model_name")
    if registered_name_tag:
        for mv in mlflow_client.search_model_versions(registered_name_tag):
            if mv.run_id == mlflow_run.info.run_id:
                registered_name = registered_name_tag
                version_number = int(mv.version)
                break
    if registered_name is None:
        for rm in mlflow_client.list_registered_models():
            for mv in mlflow_client.search_model_versions(rm.name):
                if mv.run_id == mlflow_run.info.run_id:
                    registered_name = rm.name
                    version_number = int(mv.version)
                    break
            if registered_name is not None:
                break
    if registered_name is None or version_number is None:
        raise HTTPException(status_code=409, detail="run_has_no_registered_model_version")

    pkg = ModelPackage(
        run_id=run.id,
        mlflow_run_id=mlflow_run.info.run_id,
        registered_model_name=registered_name,
        version_number=version_number,
        model_kind=model_kind,
        status="pending",
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    await enqueue("build_package", pkg.id)
    return pkg


@router.get("/model-packages/{package_id}", response_model=ModelPackageRead)
async def get_package(
    package_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelPackage:
    return await get_owned_package(db, package_id, user)


@router.get("/runs/{run_id}/packages")
async def list_packages_for_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelPackageRead]:
    await get_owned_run(db, run_id, user)
    stmt = scope_package_by_user(
        select(ModelPackage).where(ModelPackage.run_id == run_id), user
    ).order_by(ModelPackage.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [ModelPackageRead.model_validate(r) for r in rows]


@router.get("/model-packages/{package_id}/download")
async def download_package(
    package_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    pkg = await get_owned_package(db, package_id, user)
    if pkg.status != "ready" or not pkg.storage_path:
        raise HTTPException(status_code=409, detail=f"package_not_ready: status={pkg.status}")
    abs_path: Path = storage.to_absolute(pkg.storage_path)
    if not abs_path.exists():
        raise HTTPException(status_code=410, detail="package_file_missing")
    # Filename: include the run id so repeat downloads don't overwrite
    # each other in the browser's downloads dir.
    filename = f"model-package-{pkg.run_id[:8]}-v{pkg.version_number or 0}-{pkg.id[:8]}.tar.gz"
    return FileResponse(
        path=str(abs_path),
        media_type="application/gzip",
        filename=filename,
    )
