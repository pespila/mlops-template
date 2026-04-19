from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from aipacken.config import get_settings
from aipacken.db.models import Dataset, ModelCatalogEntry, Run, TransformConfig
from aipacken.docker_client.builder_client import get_builder_client
from aipacken.jobs.queue import enqueue
from aipacken.services.minio_client import presign_get
from aipacken.services.mlflow_client import create_run, ensure_experiment
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    assert uri.startswith("s3://")
    rest = uri[len("s3://") :]
    bucket, _, key = rest.partition("/")
    return bucket, key


async def train_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    settings = get_settings()

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        if run is None:
            return {"status": "missing"}

        dataset = await db.get(Dataset, run.dataset_id)
        tcfg = await db.get(TransformConfig, run.transform_config_id)
        entry = await db.get(ModelCatalogEntry, run.model_catalog_id)
        if not dataset or not tcfg or not entry:
            run.status = "failed"
            run.error_message = "missing_dependencies"
            await db.commit()
            return {"status": "failed", "reason": "missing_dependencies"}

        try:
            exp_id = ensure_experiment(f"run-{run.experiment_id}")
            mlflow_run_id = create_run(exp_id, run_name=f"run-{run.id}")
        except Exception as exc:
            logger.exception("mlflow.create_failed")
            mlflow_run_id = None

        run.mlflow_run_id = mlflow_run_id
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        bucket, key = _parse_s3_uri(dataset.storage_uri)
        dataset_uri = presign_get(bucket, key, expires_in=6 * 3600)

        env = {
            "DATASET_URI": dataset_uri,
            "TRANSFORM_CONFIG": json.dumps(
                {
                    "target_column": tcfg.target_column,
                    "transforms": tcfg.transforms_json,
                    "split": tcfg.split_json,
                    "sensitive_features": tcfg.sensitive_features or [],
                }
            ),
            "MODEL_CATALOG": json.dumps(
                {
                    "kind": entry.kind,
                    "name": entry.name,
                    "framework": entry.framework,
                    "signature": entry.signature_json,
                    "hyperparams": run.hyperparams_json,
                }
            ),
            "MLFLOW_TRACKING_URI": settings.mlflow_tracking_uri,
            "MLFLOW_RUN_ID": mlflow_run_id or "",
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "AWS_ACCESS_KEY_ID": settings.minio_root_user,
            "AWS_SECRET_ACCESS_KEY": settings.minio_root_password,
            "RUN_ID": run.id,
        }

        memory_gb = int(run.resource_limits_json.get("memory_gb", settings.training_default_memory_gb))
        cpus = int(run.resource_limits_json.get("cpus", settings.training_default_cpu))

        builder = get_builder_client()
        try:
            res = await builder.run(
                image=entry.image_uri or settings.trainer_base_image,
                env=env,
                memory_bytes=memory_gb * 1024 * 1024 * 1024,
                nano_cpus=cpus * 1_000_000_000,
                network=f"train-net-{run.id}",
                labels={"platform.run_id": run.id},
            )
        except Exception as exc:
            logger.exception("builder.run_failed")
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            await publish(f"run:{run.id}:logs", f"BUILDER_ERROR: {exc}")
            return {"status": "failed", "error": str(exc)}

        run.container_id = res["container_id"]
        await db.commit()

    # Log tailing (separate scope) — pub/sub to the frontend-visible channel.
    try:
        resp = await builder.stream_logs(res["container_id"])
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                await publish(f"run:{run_id}:logs", line[len("data: ") :])
    except Exception as exc:
        logger.warning("train_run.log_tail_error", error=str(exc))

    await enqueue("analyze_run", run_id)
    return {"status": "dispatched", "run_id": run_id, "container_id": res["container_id"]}
