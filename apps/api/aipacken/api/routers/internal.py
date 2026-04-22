from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.predictions import PredictionBulkIngest
from aipacken.config import get_settings
from aipacken.db import get_db
from aipacken.db.models import Prediction
from aipacken.services.mlflow_client import get_client, mlflow_enabled

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/mlflow/diagnostics")
async def mlflow_diagnostics() -> dict[str, object]:
    """Connectivity + configuration report for the MLflow tracking server.

    Unauthenticated on purpose — it emits no tenant data, only boolean /
    config-shape responses. Useful when standing up a fresh install or
    debugging 'my tracking URI is off' issues without shelling into the
    api container.
    """
    settings = get_settings()
    body: dict[str, object] = {
        "mlflow_backend_flag": bool(settings.mlflow_backend),
        "mlflow_tracking_uri": settings.mlflow_tracking_uri or None,
        "enabled": mlflow_enabled(),
    }
    client = get_client()
    if client is None:
        body["reachable"] = False
        body["reason"] = "mlflow_disabled" if not mlflow_enabled() else "client_init_failed"
        return body
    try:
        exps = client.search_experiments(max_results=1)
        body["reachable"] = True
        body["experiment_count_sample"] = len(exps)
    except Exception as exc:
        body["reachable"] = False
        body["reason"] = f"search_experiments_failed: {exc}"
    return body


def _verify_token(token: str | None) -> None:
    settings = get_settings()
    if token is None or not hmac.compare_digest(token, settings.internal_hmac_token):
        raise HTTPException(status_code=401, detail="invalid_internal_token")


@router.post("/predictions", status_code=202)
async def ingest_predictions(
    payload: PredictionBulkIngest,
    db: AsyncSession = Depends(get_db),
    x_internal_token: str | None = Header(default=None),
) -> dict[str, int]:
    _verify_token(x_internal_token)
    for item in payload.items:
        db.add(
            Prediction(
                deployment_id=item.deployment_id,
                received_at=item.received_at,
                latency_ms=item.latency_ms,
                mode=item.mode,
                input_ref=item.input_ref,
                output_ref=item.output_ref,
                status_code=item.status_code,
                trace_id=item.trace_id,
                input_preview_json=item.input_preview_json,
                output_preview_json=item.output_preview_json,
            )
        )
    await db.commit()
    return {"ingested": len(payload.items)}
