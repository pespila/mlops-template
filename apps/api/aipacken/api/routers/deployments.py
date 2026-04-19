from __future__ import annotations

import re
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.deployments import (
    DeploymentCreate,
    DeploymentList,
    DeploymentRead,
    PredictRequest,
    PredictResponse,
)
from aipacken.db import get_db
from aipacken.db.models import Deployment, User
from aipacken.jobs.queue import enqueue
from aipacken.services.auth import get_current_user

router = APIRouter(prefix="/deployments", tags=["deployments"])


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{s}-{uuid.uuid4().hex[:8]}" if s else f"model-{uuid.uuid4().hex[:8]}"


@router.post("", response_model=DeploymentRead, status_code=201)
async def create_deployment(
    payload: DeploymentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deployment:
    dep = Deployment(
        model_version_id=payload.model_version_id,
        name=payload.name,
        slug=_slugify(payload.name),
        status="pending",
        replicas=payload.replicas,
        audit_payloads=payload.audit_payloads,
    )
    db.add(dep)
    await db.commit()
    await db.refresh(dep)
    await enqueue("deploy_model", dep.id)
    return dep


@router.get("", response_model=DeploymentList)
async def list_deployments(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DeploymentList:
    rows = (
        await db.execute(select(Deployment).order_by(Deployment.created_at.desc()))
    ).scalars().all()
    total = (await db.execute(select(func.count()).select_from(Deployment))).scalar_one()
    return DeploymentList(
        items=[DeploymentRead.model_validate(r) for r in rows], total=total
    )


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deployment:
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="deployment_not_found")
    return dep


@router.delete("/{deployment_id}", status_code=202)
async def delete_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="deployment_not_found")
    dep.status = "tearing_down"
    await db.commit()
    await enqueue("teardown_deployment", deployment_id)
    return {"status": "tearing_down", "deployment_id": deployment_id}


@router.post("/{deployment_id}/predict", response_model=PredictResponse)
async def predict(
    deployment_id: str,
    payload: PredictRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="deployment_not_found")
    if dep.status != "active" or not dep.internal_url:
        raise HTTPException(status_code=409, detail="deployment_not_ready")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(f"{dep.internal_url}/predict", json=payload.model_dump())
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"serving_error: {exc}") from exc
        body = r.json()

    return PredictResponse(
        prediction=body.get("prediction"),
        model_version=body.get("model_version"),
        trace_id=body.get("trace_id"),
    )
