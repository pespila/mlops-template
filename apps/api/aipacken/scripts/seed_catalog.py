from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import ModelCatalogEntry

logger = structlog.get_logger(__name__)


CATALOG: list[dict[str, Any]] = [
    {
        "kind": "classification",
        "name": "sklearn_logistic",
        "framework": "scikit-learn",
        "description": "Logistic Regression (scikit-learn) — linear baseline for classification.",
        "signature_json": {
            "hyperparams": {
                "C": {"type": "float", "default": 1.0, "min": 0.0001, "max": 1000.0},
                "max_iter": {"type": "int", "default": 200, "min": 50, "max": 10000},
                "penalty": {"type": "enum", "default": "l2", "choices": ["l2", "none"]},
            },
        },
    },
    {
        "kind": "classification",
        "name": "sklearn_gradient_boosting",
        "framework": "scikit-learn",
        "description": "Gradient Boosting Classifier (scikit-learn).",
        "signature_json": {
            "hyperparams": {
                "n_estimators": {"type": "int", "default": 200, "min": 10, "max": 5000},
                "learning_rate": {"type": "float", "default": 0.1, "min": 0.001, "max": 1.0},
                "max_depth": {"type": "int", "default": 3, "min": 1, "max": 16},
            },
        },
    },
    {
        "kind": "classification",
        "name": "autogluon",
        "framework": "autogluon",
        "description": "AutoGluon TabularPredictor — zero-config AutoML.",
        "signature_json": {
            "hyperparams": {
                "time_limit": {"type": "int", "default": 600, "min": 60, "max": 36000},
                "presets": {
                    "type": "enum",
                    "default": "medium_quality",
                    "choices": [
                        "medium_quality",
                        "good_quality",
                        "high_quality",
                        "best_quality",
                    ],
                },
            },
        },
    },
]


async def seed_catalog(db: AsyncSession) -> int:
    existing = {
        e.name
        for e in (await db.execute(select(ModelCatalogEntry))).scalars().all()
    }
    count = 0
    for entry in CATALOG:
        if entry["name"] in existing:
            continue
        db.add(ModelCatalogEntry(**entry))
        count += 1
    if count:
        await db.commit()
        logger.info("seed.catalog.created", count=count)
    return count
