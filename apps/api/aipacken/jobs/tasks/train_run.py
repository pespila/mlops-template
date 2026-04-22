"""Training orchestration — spawns the trainer container, registers the model.

The worker spawns a trainer container with the platform-data volume mounted,
waits for it to exit, then:

  * metrics / artifacts / shap / bias       -> authoritative in MLflow
    (the trainer's mlflow_sink uploaded them during the run).
  * artifacts/model.pkl                     -> registered in MLflow's Model
    Registry (``create_model_version`` + ``@staging`` alias). The platform
    DB no longer stores RegisteredModel / ModelVersion rows (dropped in
    migration 0008_mlflow_b); Deployment + ModelPackage reference the
    MLflow registered-model name + version number directly.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from aipacken import storage
from aipacken.config import get_settings
from aipacken.db.models import (
    Dataset,
    Experiment,
    FeatureSchema,
    ModelCatalogEntry,
    Run,
    TransformConfig,
)
from aipacken.docker_client.builder_client import get_builder_client
from aipacken.jobs.queue import enqueue
from aipacken.services import mlflow_client
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


async def cascade_delete_run_assets(db: Any, run_id: str) -> None:
    """Remove a Run + its on-disk data + its MLflow run / registered model versions.

    Telemetry (metrics / artifacts / explanations / bias reports) lives in
    MLflow; so does the registered-model version produced on training
    success. Dropping the MLflow run first makes sure a later failure
    here doesn't leave an orphan mlflow row pointing at a deleted platform
    run. Registered-model versions produced by this run are deleted too,
    and the parent RegisteredModel is removed when it has no versions left.
    """
    # 1. Find the MLflow run and its registered-model versions.
    ml_client = mlflow_client.get_client()
    mlflow_run = mlflow_client.find_run_by_platform_id(run_id)

    if ml_client is not None and mlflow_run is not None:
        # 2. Identify every registered-model version produced by this run
        #    so we can tear them down first (they FK into the MLflow run).
        version_refs: list[tuple[str, int]] = []  # (registered_model_name, version)
        try:
            for rm in mlflow_client.list_registered_models():
                for mv in mlflow_client.search_model_versions(rm.name):
                    if mv.run_id == mlflow_run.info.run_id:
                        version_refs.append((rm.name, int(mv.version)))
        except Exception as exc:
            logger.warning("train_run.mlflow_scan_failed", run_id=run_id, error=str(exc))
        for name, version in version_refs:
            try:
                ml_client.delete_model_version(name=name, version=str(version))
            except Exception as exc:
                logger.warning(
                    "train_run.delete_model_version_failed",
                    name=name,
                    version=version,
                    error=str(exc),
                )
        # 3. Drop empty RegisteredModels.
        for name, _v in version_refs:
            try:
                remaining = mlflow_client.search_model_versions(name)
                if not remaining:
                    ml_client.delete_registered_model(name=name)
            except Exception as exc:
                logger.info(
                    "train_run.delete_registered_model_skipped",
                    name=name,
                    error=str(exc),
                )
        # 4. Finally drop the run itself.
        try:
            ml_client.delete_run(mlflow_run.info.run_id)
        except Exception as exc:
            logger.warning("train_run.mlflow_delete_failed", run_id=run_id, error=str(exc))

    # 5. On-disk cleanup for the platform run's files.
    run = await db.get(Run, run_id)
    if run is None:
        return
    await db.delete(run)
    await db.flush()

    run_root = storage.run_dir(run_id)
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)


async def _mark_run_failed(session_factory: Any, run_id: str, error: str) -> None:
    """Best-effort safety net — never leave a Run stuck in queued/running."""
    try:
        async with session_factory() as db:
            r = await db.get(Run, run_id)
            if r is None or r.status in {"succeeded", "failed", "cancelled"}:
                return
            r.status = "failed"
            r.error_message = error[:2000]
            r.finished_at = datetime.now(UTC)
            await db.commit()
    except Exception as exc:
        logger.warning("train_run.mark_failed_error", error=str(exc))


def _classify_artifact(name: str) -> tuple[str, str | None]:
    """Return (kind, content_type) for an artifact filename."""
    lower = name.lower()
    if lower.endswith(".pkl") or lower.endswith(".joblib"):
        return "model", "application/octet-stream"
    if lower.endswith(".png"):
        if "shap" in lower:
            return "shap", "image/png"
        if "bias" in lower:
            return "bias", "image/png"
        return "image", "image/png"
    if lower.endswith(".json"):
        # selected_hyperparams.json is surfaced in the "Model" section of the
        # run / model detail pages; give it a dedicated kind so the UI can
        # filter it out of the generic json artifact list.
        if lower == "selected_hyperparams.json":
            return "selected_hyperparams", "application/json"
        if lower == "input_schema.json":
            return "input_schema", "application/json"
        return "json", "application/json"
    if lower.endswith(".csv"):
        return "csv", "text/csv"
    if lower.endswith(".log") or lower.endswith(".jsonl"):
        return "logs", "text/plain"
    return "file", None


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
        # Experiment is looked up only so the trainer can tag its MLflow
        # run with a human-readable experiment name; training does not
        # depend on it being resolvable.
        experiment = await db.get(Experiment, run.experiment_id)
        if not dataset or not tcfg or not entry:
            run.status = "failed"
            run.error_message = "missing_dependencies"
            await db.commit()
            return {"status": "failed", "reason": "missing_dependencies"}

        storage.ensure_run_dirs(run_id)

        run.status = "running"
        run.started_at = datetime.now(UTC)
        await db.commit()

        dataset_rel = dataset.storage_path
        dataset_filename = Path(dataset_rel).name

        # task / hpo / roles are first-class columns on Run as of migration
        # 0004_run_task_hpo_roles. For runs that predate the migration, the
        # reserved keys may still live inside hyperparams_json — read those
        # as a fallback so historical runs continue to serve.
        raw_hp = dict(run.hyperparams_json or {})
        run_task: str | None = run.task or raw_hp.pop("_task", None)
        run_hpo: dict[str, Any] | None = run.hpo_json or raw_hp.pop("_hpo", None)
        run_roles: dict[str, Any] | None = run.roles_json or raw_hp.pop("_roles", None)
        # Drop the reserved keys even when new columns had values — they
        # should never reach the trainer as "hyperparams".
        for _k in ("_task", "_hpo", "_roles"):
            raw_hp.pop(_k, None)
        resolved_task = run_task or entry.kind

        # User-authored column types (set via PATCH /datasets/{id}/schema/{col}).
        # Forwarded so the trainer can override pandas dtype inference — e.g.
        # a date column stored as string reaches the date-feature expander.
        from sqlalchemy import select as _select

        feature_rows = (
            (await db.execute(_select(FeatureSchema).where(FeatureSchema.dataset_id == dataset.id)))
            .scalars()
            .all()
        )
        semantic_types = {r.column_name: r.semantic_type for r in feature_rows if r.semantic_type}

        env = {
            "RUN_ID": run.id,
            "DATA_ROOT": settings.data_root,
            "DATASET_PATH": f"{settings.data_root}/{dataset_rel}",
            "DATASET_FILENAME": dataset_filename,
            "RUN_DIR": f"{settings.data_root}/runs/{run.id}",
            # Trainer signs every model.pkl it writes so the serving container
            # + any later platform-side joblib.load refuses unsigned or
            # tampered pickles. Must match what serving / build_package use.
            "INTERNAL_HMAC_TOKEN": settings.internal_hmac_token,
            # MLflow — trainer uploads via the proxied-artifact path
            # (Batch 35c set --default-artifact-root=mlflow-artifacts:/
            # on the mlflow service). MLflow itself then writes to S3
            # using its own AWS_* creds; the trainer only needs the
            # tracking URI. No MinIO credentials leak to clients.
            "MLFLOW_TRACKING_URI": os.environ.get("MLFLOW_TRACKING_URI", ""),
            "MLFLOW_EXPERIMENT_NAME": (experiment.name if experiment is not None else "default"),
            # mlflow's Python client tries to stamp a git SHA onto every
            # run for reproducibility. The trainer image has no git;
            # silence the noisy warning instead of bloating the image.
            "GIT_PYTHON_REFRESH": "quiet",
            "TRANSFORM_CONFIG": json.dumps(
                {
                    "target": tcfg.target_column,
                    "transforms": tcfg.transforms_json or [],
                    "split": tcfg.split_json or {"train": 0.7, "val": 0.15, "test": 0.15},
                    "sensitive_features": tcfg.sensitive_features or [],
                    "roles": run_roles or {},
                    "semantic_types": semantic_types,
                }
            ),
            "SENSITIVE_FEATURES": json.dumps(tcfg.sensitive_features or []),
            "MODEL_CATALOG": json.dumps(
                {
                    "kind": entry.name,
                    "task": resolved_task,
                    "name": entry.name,
                    "framework": entry.framework,
                    "signature": entry.signature_json,
                    "hyperparams": raw_hp,
                    "hpo": run_hpo,
                }
            ),
        }

        memory_gb = int(
            run.resource_limits_json.get("memory_gb", settings.training_default_memory_gb)
        )
        cpus = int(run.resource_limits_json.get("cpus", settings.training_default_cpu))

        builder = get_builder_client()
        try:
            res = await builder.run(
                image=entry.image_uri or settings.trainer_base_image,
                env=env,
                memory_bytes=memory_gb * 1024 * 1024 * 1024,
                nano_cpus=cpus * 1_000_000_000,
                # Training needs no outbound network — data is on the volume.
                # Use platform-net for now so `make dev` on Docker Desktop can
                # create containers without a per-job network; tighten to `none`
                # in v1 once we validate across Docker variants.
                network="platform-net",
                labels={"platform.run_id": run.id},
                mounts=[
                    {
                        "source": "platform-data",
                        "target": settings.data_root,
                        "read_only": False,
                    }
                ],
            )
        except Exception as exc:
            logger.exception("builder.run_failed")
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = datetime.now(UTC)
            await db.commit()
            await publish(f"run:{run.id}:logs", f"BUILDER_ERROR: {exc}")
            return {"status": "failed", "error": str(exc)}

        run.container_id = res["container_id"]
        await db.commit()

    # Log tailing — pub/sub to the frontend-visible channel AND accumulate a
    # local buffer so we can persist a full transcript on exit.
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

    exit_code = -1
    try:
        wait_res = await builder.wait(res["container_id"])
        exit_code = int(wait_res.get("exit_code", -1))
    except Exception as exc:
        logger.warning("train_run.wait_failed", error=str(exc))

    # Fallback: even if the streaming tail caught nothing (container died
    # mid-import, stream RTT lost the first chunk, etc.), pull the full
    # persisted log buffer via the one-shot /logs endpoint after wait.
    # Docker retains stdout+stderr until the container is removed.
    if not captured_lines:
        try:
            fallback = await builder.logs(res["container_id"], tail=2000)
            for text in fallback.get("lines", []) or []:
                captured_lines.append(text)
                await publish(f"run:{run_id}:logs", text)
            if captured_lines:
                logger.info(
                    "train_run.log_fallback_recovered",
                    run_id=run_id,
                    lines=len(captured_lines),
                )
        except Exception as exc:
            logger.warning("train_run.log_fallback_error", error=str(exc))

    run_root = storage.run_dir(run_id)
    artifacts_root = storage.run_artifacts_dir(run_id)
    logs_path = storage.run_logs_path(run_id)

    # Persist the captured log transcript to the volume before we exit the
    # worker's scope — refresh of the run detail page then replays it.
    if captured_lines:
        try:
            logs_path.write_text("\n".join(captured_lines))
        except Exception as exc:
            logger.warning("train_run.log_persist_failed", error=str(exc))

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        if run is None:
            return {"status": "missing"}

        # Training logs no longer create an Artifact row (table dropped
        # in migration 0007_mlflow_a). The trainer's mlflow_sink already
        # uploaded `reports/` + `artifacts/` + `metrics.jsonl` to MLflow
        # on the success path; the logs_path file on disk is still
        # served directly by the SSE log endpoint for live viewing.

        if exit_code != 0:
            run.status = "failed"
            run.error_message = f"trainer exited with code {exit_code}"
            run.finished_at = datetime.now(UTC)
            await db.commit()
            return {"status": "failed", "exit_code": exit_code}

        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        await db.commit()

    # --- Metrics / artifacts / SHAP / bias / MLflow registry ---------------
    # Metrics, artifacts, SHAP, and bias are authoritative in MLflow
    # (migration 0007_mlflow_a dropped their mirror tables); the trainer's
    # mlflow_sink uploaded metrics.jsonl + artifacts/* + reports/* during
    # the run. Readers go through aipacken.services.mlflow_client.
    #
    # What's left here is the model-registry write: classify the model
    # artifact so Deployment/ModelPackage can snapshot the kind, then
    # call MLflow's ``create_model_version`` so the MLflow registry owns
    # the "which run produced which version of which model" mapping. An
    # ``@staging`` alias is set so promotion is a single alias move later.
    model_artifact_name: str | None = None
    model_kind = "sklearn"
    if artifacts_root.exists():
        for entry_path in sorted(artifacts_root.iterdir()):
            kind, _ = _classify_artifact(entry_path.name)
            if entry_path.is_dir():
                if kind == "file":
                    kind = "model"
                if kind == "model":
                    model_artifact_name = entry_path.name
                    model_kind = (
                        "autogluon" if "autogluon" in entry_path.name.lower() else "sklearn"
                    )
                continue
            if kind == "model" and model_artifact_name is None:
                model_artifact_name = entry_path.name

    if model_artifact_name:
        try:
            mlflow_run = mlflow_client.find_run_by_platform_id(run_id)
            if mlflow_run is not None:
                registered_name = f"{entry.name}-run-{run_id[:8]}"
                # The trainer uploaded everything under ``artifacts/`` inside
                # the MLflow run, so the registered model's source URI is
                # ``runs:/<mlflow_run_id>/artifacts/<filename_or_dir>``.
                source_uri = f"runs:/{mlflow_run.info.run_id}/artifacts/{model_artifact_name}"
                mv = mlflow_client.register_model_version(
                    name=registered_name,
                    source_uri=source_uri,
                    run_id=mlflow_run.info.run_id,
                    description=entry.description,
                    tags={
                        "platform.run_id": run_id,
                        "platform.model_kind": model_kind,
                        "platform.experiment_id": run.experiment_id,
                        "platform.catalog_name": entry.name,
                    },
                )
                if mv is not None:
                    mlflow_client.set_alias(registered_name, "staging", str(mv.version))
                    # Tag the tracking-level run with the registered model
                    # info so the UI / Deployment resolver can look it up
                    # in a single MLflow call rather than scanning versions.
                    try:
                        client = mlflow_client.get_client()
                        if client is not None:
                            client.set_tag(
                                mlflow_run.info.run_id,
                                "platform.registered_model_name",
                                registered_name,
                            )
                            client.set_tag(
                                mlflow_run.info.run_id,
                                "platform.registered_model_version",
                                str(mv.version),
                            )
                            client.set_tag(
                                mlflow_run.info.run_id,
                                "platform.model_kind",
                                model_kind,
                            )
                    except Exception as exc:
                        logger.info("train_run.run_tag_failed", run_id=run_id, error=str(exc))

                    # Copy the input_schema.json into the Deployment-owned
                    # snapshot location at deploy time, not here — it stays
                    # in the MLflow artifact store until a Deployment pulls it.
                    _ = json  # json import retained below for other writes
        except Exception as exc:
            logger.warning("train_run.model_register_failed", error=str(exc))

    await enqueue("analyze_run", run_id)
    return {
        "status": "succeeded",
        "run_id": run_id,
        "exit_code": exit_code,
        "run_root": str(run_root),
    }
