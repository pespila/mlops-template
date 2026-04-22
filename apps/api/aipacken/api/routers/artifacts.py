"""Artifact download endpoint — proxies to MLflow.

Post-Batch-35a: the ``artifacts`` DB table is gone. Artifact identity is
an opaque ``<mlflow_run_id>:<relative_path>`` string that the frontend
receives from ``GET /api/runs/{id}/artifacts``. This endpoint
authenticates the caller, verifies they own the platform run that the
MLflow run is tagged with, downloads the file from MLflow to a temp path,
and streams it back.

Kept on our api (instead of redirecting the SPA at MLflow directly) so:
  * session cookies + rate limits + audit logging stay in one place,
  * MLflow's own auth story (none) does not leak to the browser,
  * MLflow's internal path layout is an implementation detail we can
    swap later without a frontend change.
"""

from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.authz import get_owned_run
from aipacken.db import get_db
from aipacken.db.models import User
from aipacken.services import mlflow_client
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _split_artifact_id(artifact_id: str) -> tuple[str, str]:
    """Artifact id is ``<mlflow_run_id>:<path/inside/run>``.

    Raises 400 if the shape is wrong — the only legitimate producer is
    ``mlflow_client.list_run_artifacts``, so a malformed value is always
    a client or tamper issue.
    """
    if ":" not in artifact_id:
        raise HTTPException(status_code=400, detail="invalid_artifact_id")
    mlflow_run_id, rel_path = artifact_id.split(":", 1)
    if not mlflow_run_id or not rel_path or ".." in rel_path:
        raise HTTPException(status_code=400, detail="invalid_artifact_id")
    return mlflow_run_id, rel_path


@router.get("/download")
async def download_artifact(
    id: str = Query(..., description="Artifact id from /api/runs/{run}/artifacts"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    mlflow_run_id, rel_path = _split_artifact_id(id)

    # Authorization: resolve the MLflow run to a platform_run_id tag,
    # then verify ownership via our DB.
    client = mlflow_client.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="mlflow_unavailable")
    try:
        run = client.get_run(mlflow_run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="artifact_not_found") from exc
    platform_run_id = (run.data.tags or {}).get("platform.run_id")
    if not platform_run_id:
        raise HTTPException(status_code=403, detail="mlflow_run_not_platform_owned")
    await get_owned_run(db, platform_run_id, user)

    # Download the specific file into a process-scoped temp dir. MLflow
    # returns the local path; FileResponse streams it back and we let the
    # tempdir clean itself up on process exit.
    try:
        import mlflow  # type: ignore[import-not-found]

        local = mlflow.artifacts.download_artifacts(
            run_id=mlflow_run_id,
            artifact_path=rel_path,
            dst_path=tempfile.mkdtemp(prefix="aipacken-art-"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"artifact_download_failed: {exc}") from exc
    path = Path(local)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact_not_a_file")

    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path=path, media_type=content_type, filename=path.name)
