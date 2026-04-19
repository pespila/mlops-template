from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from aipacken.config import get_settings
from aipacken.db.models import (
    Artifact,
    Dataset,
    Metric,
    ModelCatalogEntry,
    ModelVersion,
    RegisteredModel,
    Run,
    TransformConfig,
)
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


async def _mark_run_failed(session_factory: Any, run_id: str, error: str) -> None:
    """Best-effort safety net — never leave a Run stuck in queued/running."""
    try:
        async with session_factory() as db:
            r = await db.get(Run, run_id)
            if r is None or r.status in {"succeeded", "failed", "cancelled"}:
                return
            r.status = "failed"
            r.error_message = error[:2000]
            r.finished_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("train_run.mark_failed_error", error=str(exc))


async def train_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    try:
        return await _train_run_inner(ctx, run_id)
    except Exception as exc:
        logger.exception("train_run.fatal")
        await _mark_run_failed(ctx["session_factory"], run_id, f"{type(exc).__name__}: {exc}")
        await publish(f"run:{run_id}:logs", f"FATAL: {type(exc).__name__}: {exc}")
        raise


async def _train_run_inner(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
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
                    "target": tcfg.target_column,
                    "target_column": tcfg.target_column,  # alias for older trainer images
                    "transforms": tcfg.transforms_json or [],
                    "split": tcfg.split_json or {"train": 0.7, "val": 0.15, "test": 0.15},
                    "sensitive_features": tcfg.sensitive_features or [],
                }
            ),
            "SENSITIVE_FEATURES": json.dumps(tcfg.sensitive_features or []),
            "ARTIFACT_BUCKET": settings.s3_bucket_artifacts,
            "MLFLOW_EXPERIMENT_ID": exp_id or "",
            "MODEL_CATALOG": json.dumps(
                {
                    # Trainer adapters key off `kind` — pass the model identifier
                    # (`sklearn_logistic`, `autogluon`, ...), not the ML task.
                    "kind": entry.name,
                    "task": entry.kind,
                    "name": entry.name,
                    "framework": entry.framework,
                    "signature": entry.signature_json,
                    "hyperparams": run.hyperparams_json,
                }
            ),
            "MLFLOW_TRACKING_URI": settings.mlflow_tracking_uri,
            "MLFLOW_RUN_ID": mlflow_run_id or "",
            # MLflow's S3 artifact backend needs the endpoint URL under its
            # own env name (MLFLOW_S3_ENDPOINT_URL). Without it boto3 defaults
            # to real AWS S3 and our MinIO creds get rejected.
            "MLFLOW_S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "AWS_ACCESS_KEY_ID": settings.minio_root_user,
            "AWS_SECRET_ACCESS_KEY": settings.minio_root_password,
            "AWS_DEFAULT_REGION": settings.s3_region,
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
                # v0: share platform-net so the trainer can reach MinIO + MLflow.
                # v1: spin up an ephemeral train-net-{run.id} with a proxy to only those two.
                network="platform-net",
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

    # Log tailing (separate scope) — pub/sub to the frontend-visible channel
    # AND accumulate a local buffer so we can persist a full transcript when
    # the container exits.
    captured_lines: list[str] = []
    try:
        resp = await builder.stream_logs(res["container_id"])
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                text = line[len("data: ") :]
                captured_lines.append(text)
                await publish(f"run:{run_id}:logs", text)
    except Exception as exc:
        logger.warning("train_run.log_tail_error", error=str(exc))

    # Container exited — block for the final exit code so we know success/fail.
    exit_code = -1
    try:
        wait_res = await builder.wait(res["container_id"])
        exit_code = int(wait_res.get("exit_code", -1))
    except Exception as exc:
        logger.warning("train_run.wait_failed", error=str(exc))

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        if run is None:
            return {"status": "missing"}

        # Persist logs to MinIO + register an Artifact row so refresh shows history.
        if captured_lines:
            import io as _io

            from aipacken.services.minio_client import upload_fileobj

            log_bytes = "\n".join(captured_lines).encode("utf-8")
            log_key = f"{run_id}/logs/training.log"
            try:
                upload_fileobj(
                    _io.BytesIO(log_bytes),
                    bucket=settings.s3_bucket_artifacts,
                    key=log_key,
                    content_type="text/plain",
                )
                db.add(
                    Artifact(
                        run_id=run_id,
                        kind="logs",
                        uri=f"s3://{settings.s3_bucket_artifacts}/{log_key}",
                        size_bytes=len(log_bytes),
                        content_type="text/plain",
                    )
                )
            except Exception as exc:
                logger.warning("train_run.log_persist_failed", error=str(exc))

        if exit_code != 0:
            run.status = "failed"
            run.error_message = f"trainer exited with code {exit_code}"
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "failed", "exit_code": exit_code}

        # Success path: sync metrics + model from MLflow into our own tables.
        if mlflow_run_id:
            try:
                from aipacken.services.mlflow_client import get_mlflow_client

                mc = get_mlflow_client()
                mlflow_run = mc.get_run(mlflow_run_id)
                for name, value in (mlflow_run.data.metrics or {}).items():
                    db.add(Metric(run_id=run_id, name=name, value=float(value)))

                artifact_uri = mlflow_run.info.artifact_uri
                model_uri = f"{artifact_uri}/model"
                db.add(
                    Artifact(
                        run_id=run_id,
                        kind="model",
                        uri=model_uri,
                        content_type="application/x-mlflow-pyfunc",
                    )
                )

                # Register a platform-side ModelVersion so the Deploy button appears.
                model_name = f"{entry.name}-run-{run_id[:8]}"
                reg = RegisteredModel(name=model_name, description=entry.description)
                db.add(reg)
                await db.flush()
                db.add(
                    ModelVersion(
                        registered_model_id=reg.id,
                        run_id=run_id,
                        mlflow_version="1",
                        stage="staging",
                        input_schema_json={},
                        output_schema_json={},
                    )
                )
            except Exception as exc:
                logger.warning("train_run.mlflow_sync_failed", error=str(exc))

        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()

    await enqueue("analyze_run", run_id)
    return {"status": "succeeded", "run_id": run_id, "exit_code": exit_code}
