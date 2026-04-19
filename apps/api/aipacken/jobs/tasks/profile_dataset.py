from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import select

from aipacken.config import get_settings
from aipacken.db.models import Dataset, FeatureSchema
from aipacken.services.minio_client import download_fileobj, upload_fileobj
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    assert uri.startswith("s3://")
    _, _, rest = uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    return bucket, key


def _infer_semantic(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    n_unique = series.nunique(dropna=True)
    if 0 < n_unique <= max(20, int(0.05 * len(series))):
        return "categorical"
    return "text"


async def profile_dataset(ctx: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    settings = get_settings()

    async with session_factory() as db:
        dataset = await db.get(Dataset, dataset_id)
        if dataset is None:
            logger.warning("profile_dataset.missing", dataset_id=dataset_id)
            return {"status": "missing"}

        dataset.status = "profiling"
        await db.commit()
        await publish(f"dataset:{dataset_id}:status", {"status": "profiling"})

        bucket, key = _parse_s3_uri(dataset.storage_uri)
        buf = io.BytesIO()
        download_fileobj(bucket, key, buf)
        buf.seek(0)

        try:
            df = pd.read_csv(buf)
        except Exception as exc:
            logger.exception("profile_dataset.read_failed")
            dataset.status = "error"
            await db.commit()
            await publish(f"dataset:{dataset_id}:status", {"status": "error", "error": str(exc)})
            return {"status": "error", "error": str(exc)}

        dataset.row_count = int(df.shape[0])
        dataset.col_count = int(df.shape[1])

        summary: dict[str, Any] = {
            "row_count": dataset.row_count,
            "col_count": dataset.col_count,
            "columns": {},
        }

        existing = (
            await db.execute(select(FeatureSchema).where(FeatureSchema.dataset_id == dataset_id))
        ).scalars().all()
        for row in existing:
            await db.delete(row)
        await db.flush()

        for col in df.columns:
            series = df[col]
            missing_pct = float(series.isna().mean() * 100)
            unique_count = int(series.nunique(dropna=True))
            stats: dict[str, Any] = {"count": int(series.count())}
            if pd.api.types.is_numeric_dtype(series):
                desc = series.describe()
                stats.update(
                    {
                        "mean": float(desc.get("mean", 0.0)),
                        "std": float(desc.get("std", 0.0)),
                        "min": float(desc.get("min", 0.0)),
                        "max": float(desc.get("max", 0.0)),
                    }
                )
            fs = FeatureSchema(
                dataset_id=dataset_id,
                column_name=str(col),
                inferred_type=str(series.dtype),
                semantic_type=_infer_semantic(series),
                stats_json=stats,
                missing_pct=missing_pct,
                unique_count=unique_count,
            )
            db.add(fs)
            summary["columns"][str(col)] = {
                "dtype": str(series.dtype),
                "semantic": _infer_semantic(series),
                "missing_pct": missing_pct,
                "unique_count": unique_count,
            }

        summary_bytes = json.dumps(summary, default=str).encode("utf-8")
        profile_key = f"{dataset_id}/profile/summary.json"
        upload_fileobj(
            io.BytesIO(summary_bytes),
            bucket=settings.s3_bucket_reports,
            key=profile_key,
            content_type="application/json",
        )
        dataset.profile_uri = f"s3://{settings.s3_bucket_reports}/{profile_key}"
        dataset.profile_summary_json = summary
        dataset.status = "ready"
        await db.commit()
        await publish(f"dataset:{dataset_id}:status", {"status": "ready"})

        return {"status": "ready", "dataset_id": dataset_id}
