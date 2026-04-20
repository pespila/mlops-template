from __future__ import annotations

import json
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import select

from aipacken import storage
from aipacken.db.models import Dataset, FeatureSchema
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


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

    async with session_factory() as db:
        dataset = await db.get(Dataset, dataset_id)
        if dataset is None:
            logger.warning("profile_dataset.missing", dataset_id=dataset_id)
            return {"status": "missing"}

        dataset.status = "profiling"
        await db.commit()
        await publish(f"dataset:{dataset_id}:status", {"status": "profiling"})

        src = storage.to_absolute(dataset.storage_path)
        try:
            df = pd.read_csv(src)
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

        profile_path = storage.dataset_profile_path(dataset_id)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(summary, default=str))

        dataset.profile_path = storage.to_relative(profile_path)
        dataset.profile_summary_json = summary
        dataset.status = "ready"
        await db.commit()
        await publish(f"dataset:{dataset_id}:status", {"status": "ready"})

        return {"status": "ready", "dataset_id": dataset_id}
