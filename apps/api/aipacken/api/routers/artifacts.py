"""Artifact download endpoint — serves files off the platform-data volume."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken import storage
from aipacken.api.authz import get_owned_artifact
from aipacken.db import get_db
from aipacken.db.models import User
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    art = await get_owned_artifact(db, artifact_id, user)

    try:
        path = storage.to_absolute(art.uri)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_artifact_path") from exc

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact_missing")

    return FileResponse(
        path=path,
        media_type=art.content_type or "application/octet-stream",
        filename=path.name,
    )
