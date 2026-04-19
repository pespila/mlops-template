from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.schemas.predictions import PredictionBulkIngest
from aipacken.config import get_settings
from aipacken.db import get_db
from aipacken.db.models import Prediction

router = APIRouter(prefix="/internal", tags=["internal"])


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
