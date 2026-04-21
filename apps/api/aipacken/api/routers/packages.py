"""Downloadable deployment packages for ModelVersions.

Packages are built asynchronously by the ``build_package`` worker job and
streamed back on demand. Each ``ModelVersion`` can have multiple packages
over time; the frontend surfaces the latest one per version.
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
from aipacken.db import get_db
from aipacken.db.models import ModelPackage, ModelVersion, RegisteredModel, User
from aipacken.jobs.queue import enqueue
from aipacken.services.auth import get_current_user

router = APIRouter(tags=["packages"])


class ModelPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_version_id: str
    status: str
    storage_path: str | None = None
    size_bytes: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


@router.post(
    "/models/{model_id}/versions/{version_id}/package",
    response_model=ModelPackageRead,
    status_code=201,
)
async def create_package(
    model_id: str,
    version_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModelPackage:
    """Kick off a new package build for a specific version.

    Re-triggering always creates a fresh row — older packages stay on disk
    until the cleanup job prunes them, so the user can still download in-flight
    builds while a newer one assembles.
    """
    rm = await db.get(RegisteredModel, model_id)
    if rm is None:
        raise HTTPException(status_code=404, detail="model_not_found")
    mv = await db.get(ModelVersion, version_id)
    if mv is None or mv.registered_model_id != model_id:
        raise HTTPException(status_code=404, detail="version_not_found")
    if not mv.storage_path:
        raise HTTPException(status_code=409, detail="version_has_no_artifact")

    pkg = ModelPackage(model_version_id=version_id, status="pending")
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
    pkg = await db.get(ModelPackage, package_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="package_not_found")
    return pkg


@router.get("/models/{model_id}/versions/{version_id}/packages")
async def list_packages_for_version(
    model_id: str,
    version_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelPackageRead]:
    mv = await db.get(ModelVersion, version_id)
    if mv is None or mv.registered_model_id != model_id:
        raise HTTPException(status_code=404, detail="version_not_found")
    rows = (
        await db.execute(
            select(ModelPackage)
            .where(ModelPackage.model_version_id == version_id)
            .order_by(ModelPackage.created_at.desc())
        )
    ).scalars().all()
    return [ModelPackageRead.model_validate(r) for r in rows]


@router.get("/model-packages/{package_id}/download")
async def download_package(
    package_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    pkg = await db.get(ModelPackage, package_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="package_not_found")
    if pkg.status != "ready" or not pkg.storage_path:
        raise HTTPException(status_code=409, detail=f"package_not_ready: status={pkg.status}")
    abs_path: Path = storage.to_absolute(pkg.storage_path)
    if not abs_path.exists():
        raise HTTPException(status_code=410, detail="package_file_missing")
    # Filename: include the model version id so repeat downloads don't
    # overwrite each other in the browser's downloads dir.
    filename = f"model-package-{pkg.model_version_id}-{pkg.id[:8]}.tar.gz"
    return FileResponse(
        path=str(abs_path),
        media_type="application/gzip",
        filename=filename,
    )
