"""Training orchestration — pure filesystem, no S3/MLflow in sight.

The worker spawns a trainer container with the platform-data volume mounted,
waits for it to exit, then walks the run directory and mirrors:

  metrics.jsonl        -> Metric rows
  artifacts/*          -> Artifact rows
  reports/shap.json    -> ExplanationArtifact row
  reports/bias.json    -> BiasReport rows
  artifacts/model.pkl  -> RegisteredModel + ModelVersion rows

Each of those five steps commits independently so a later failure doesn't
roll back earlier successes.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from aipacken import storage
from aipacken.config import get_settings
from aipacken.db.models import (
    Artifact,
    BiasReport,
    Dataset,
    ExplanationArtifact,
    Metric,
    ModelCatalogEntry,
    ModelVersion,
    RegisteredModel,
    Run,
    TransformConfig,
)
from aipacken.docker_client.builder_client import get_builder_client
from aipacken.jobs.queue import enqueue
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


async def cascade_delete_run_assets(db: Any, run_id: str) -> None:
    """Remove a Run, its on-disk data, and every ModelVersion it produced.

    Metrics, Artifacts, ExplanationArtifact, and BiasReport rows cascade via
    the FK `ondelete=CASCADE`. RegisteredModel rows are left alone when they
    still have surviving versions; removed when this run's versions were the
    last ones.
    """
    from sqlalchemy import select as _select

    run = await db.get(Run, run_id)
    if run is None:
        return

    mv_ids = (
        await db.execute(_select(ModelVersion.id).where(ModelVersion.run_id == run_id))
    ).scalars().all()
    reg_ids: set[str] = set()
    for mv_id in mv_ids:
        mv = await db.get(ModelVersion, mv_id)
        if mv is None:
            continue
        reg_ids.add(mv.registered_model_id)
        mv_dir = storage.model_version_dir(mv_id)
        if mv_dir.exists():
            shutil.rmtree(mv_dir, ignore_errors=True)
        await db.delete(mv)

    await db.delete(run)
    await db.flush()

    # Drop RegisteredModel rows that no longer have any versions.
    for reg_id in reg_ids:
        remaining = (
            await db.execute(
                _select(ModelVersion.id).where(ModelVersion.registered_model_id == reg_id)
            )
        ).scalars().first()
        if remaining is None:
            reg = await db.get(RegisteredModel, reg_id)
            if reg is not None:
                await db.delete(reg)

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
            r.finished_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
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
        if not dataset or not tcfg or not entry:
            run.status = "failed"
            run.error_message = "missing_dependencies"
            await db.commit()
            return {"status": "failed", "reason": "missing_dependencies"}

        storage.ensure_run_dirs(run_id)

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        dataset_rel = dataset.storage_path
        dataset_filename = Path(dataset_rel).name

        env = {
            "RUN_ID": run.id,
            "DATA_ROOT": settings.data_root,
            "DATASET_PATH": f"{settings.data_root}/{dataset_rel}",
            "DATASET_FILENAME": dataset_filename,
            "RUN_DIR": f"{settings.data_root}/runs/{run.id}",
            "TRANSFORM_CONFIG": json.dumps(
                {
                    "target": tcfg.target_column,
                    "transforms": tcfg.transforms_json or [],
                    "split": tcfg.split_json or {"train": 0.7, "val": 0.15, "test": 0.15},
                    "sensitive_features": tcfg.sensitive_features or [],
                }
            ),
            "SENSITIVE_FEATURES": json.dumps(tcfg.sensitive_features or []),
            "MODEL_CATALOG": json.dumps(
                {
                    "kind": entry.name,
                    "task": entry.kind,
                    "name": entry.name,
                    "framework": entry.framework,
                    "signature": entry.signature_json,
                    "hyperparams": run.hyperparams_json,
                }
            ),
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
            run.finished_at = datetime.now(timezone.utc)
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

    run_root = storage.run_dir(run_id)
    artifacts_root = storage.run_artifacts_dir(run_id)
    reports_root = storage.run_reports_dir(run_id)
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

        if logs_path.exists():
            try:
                db.add(
                    Artifact(
                        run_id=run_id,
                        kind="logs",
                        name="training.log",
                        uri=storage.to_relative(logs_path),
                        size_bytes=logs_path.stat().st_size,
                        content_type="text/plain",
                    )
                )
                await db.commit()
            except Exception as exc:
                logger.warning("train_run.log_artifact_failed", error=str(exc))

        if exit_code != 0:
            run.status = "failed"
            run.error_message = f"trainer exited with code {exit_code}"
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "failed", "exit_code": exit_code}

        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()

    # --- Step 1: metrics -----------------------------------------------------
    metrics_path = storage.run_metrics_path(run_id)
    if metrics_path.exists():
        try:
            rows: list[dict[str, Any]] = []
            for raw in metrics_path.read_text().splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
            async with session_factory() as db2:
                for row in rows:
                    name = str(row.get("name", "")).strip()
                    if not name:
                        continue
                    try:
                        value = float(row.get("value"))
                    except (TypeError, ValueError):
                        continue
                    db2.add(
                        Metric(
                            run_id=run_id,
                            name=name,
                            value=value,
                            step=int(row["step"]) if "step" in row else None,
                            phase=row.get("phase"),
                        )
                    )
                await db2.commit()
        except Exception as exc:
            logger.warning("train_run.metric_sync_failed", error=str(exc))

    # --- Step 2: artifacts + model pointer -----------------------------------
    model_artifact_rel: str | None = None
    model_kind = "sklearn"
    if artifacts_root.exists():
        try:
            async with session_factory() as db2:
                for entry_path in sorted(artifacts_root.iterdir()):
                    kind, content_type = _classify_artifact(entry_path.name)
                    if entry_path.is_dir():
                        # AutoGluon predictor directory — treat as a single "model" artifact.
                        if kind == "file":
                            kind = "model"
                            content_type = "application/x-directory"
                        if kind == "model":
                            model_artifact_rel = storage.to_relative(entry_path)
                            model_kind = "autogluon" if "autogluon" in entry_path.name.lower() else "sklearn"
                        total = sum(p.stat().st_size for p in entry_path.rglob("*") if p.is_file())
                        db2.add(
                            Artifact(
                                run_id=run_id,
                                kind=kind,
                                name=entry_path.name,
                                uri=storage.to_relative(entry_path),
                                size_bytes=total,
                                content_type=content_type,
                            )
                        )
                        continue
                    if kind == "model" and model_artifact_rel is None:
                        model_artifact_rel = storage.to_relative(entry_path)
                    db2.add(
                        Artifact(
                            run_id=run_id,
                            kind=kind,
                            name=entry_path.name,
                            uri=storage.to_relative(entry_path),
                            size_bytes=entry_path.stat().st_size,
                            content_type=content_type,
                        )
                    )
                await db2.commit()
        except Exception as exc:
            logger.warning("train_run.artifact_sync_failed", error=str(exc))

    # --- Step 3: SHAP --------------------------------------------------------
    shap_report_path = reports_root / "shap.json"
    if shap_report_path.exists():
        try:
            shap_doc = json.loads(shap_report_path.read_text())
            async with session_factory() as db2:
                db2.add(
                    ExplanationArtifact(
                        run_id=run_id,
                        kind="shap_global",
                        feature_importance_json=shap_doc.get("global_importance", {}),
                        artifact_path=storage.to_relative(shap_report_path),
                    )
                )
                await db2.commit()
        except Exception as exc:
            logger.info("train_run.shap_sync_failed", error=str(exc))

    # --- Step 4: bias --------------------------------------------------------
    bias_report_path = reports_root / "bias.json"
    if bias_report_path.exists():
        try:
            bias_doc = json.loads(bias_report_path.read_text())
            groups = bias_doc.get("groups") or {}
            overall = bias_doc.get("overall")
            overall_scalar = float(overall) if isinstance(overall, (int, float)) else None
            # Prefer the sensitive column names the trainer stamped; fall back
            # to "combined" so we never blow past the VARCHAR(255) limit with
            # joined group labels like "4.3|2.0|1.1|0.1,..." .
            sens_cols = bias_doc.get("sensitive_features") or []
            sens_label = (",".join(str(c) for c in sens_cols))[:255] if sens_cols else "combined"
            async with session_factory() as db2:
                db2.add(
                    BiasReport(
                        run_id=run_id,
                        sensitive_feature=sens_label,
                        metric_name=str(bias_doc.get("metric") or "accuracy"),
                        group_values_json={
                            "groups": groups,
                            "deltas": bias_doc.get("deltas") or {},
                            "overall": overall,
                            "sensitive_features": sens_cols,
                            "groups_truncated": bias_doc.get("groups_truncated", False),
                            "groups_total": bias_doc.get("groups_total"),
                        },
                        overall_value=overall_scalar,
                        report_path=storage.to_relative(bias_report_path),
                    )
                )
                await db2.commit()
        except Exception as exc:
            logger.info("train_run.bias_sync_failed", error=str(exc))

    # --- Step 5: RegisteredModel + ModelVersion ------------------------------
    if model_artifact_rel:
        try:
            async with session_factory() as db2:
                model_name = f"{entry.name}-run-{run_id[:8]}"
                reg = RegisteredModel(name=model_name, description=entry.description)
                db2.add(reg)
                await db2.flush()

                # Pick up the input_schema.json the trainer wrote so serving
                # containers + the deployment UI can load it without a live
                # probe.
                input_schema: dict[str, Any] = {}
                schema_file = storage.run_artifacts_dir(run_id) / "input_schema.json"
                if schema_file.exists():
                    try:
                        input_schema = json.loads(schema_file.read_text())
                    except Exception as exc:
                        logger.info("train_run.schema_read_failed", error=str(exc))

                mv = ModelVersion(
                    registered_model_id=reg.id,
                    run_id=run_id,
                    version=1,
                    stage="staging",
                    model_kind=model_kind,
                    input_schema_json=input_schema,
                    output_schema_json={},
                )
                db2.add(mv)
                await db2.flush()

                # Promote the run artifact into a stable models/{mv_id}/ location
                # so the source Run can be pruned independently from deployments.
                mv_dir = storage.model_version_dir(mv.id)
                mv_dir.mkdir(parents=True, exist_ok=True)
                src_abs = storage.to_absolute(model_artifact_rel)
                if src_abs.is_dir():
                    dst = mv_dir / src_abs.name
                    if not dst.exists():
                        shutil.copytree(src_abs, dst)
                    mv.storage_path = storage.to_relative(dst)
                else:
                    dst = mv_dir / src_abs.name
                    try:
                        if not dst.exists():
                            dst.hardlink_to(src_abs)
                    except OSError:
                        shutil.copy2(src_abs, dst)
                    mv.storage_path = storage.to_relative(dst)

                # The serving loader looks for input_schema.json next to the
                # model artifact — copy it into the model version dir too so
                # runs can be pruned without breaking already-deployed models.
                schema_src = storage.run_artifacts_dir(run_id) / "input_schema.json"
                if schema_src.exists():
                    shutil.copy2(schema_src, mv_dir / "input_schema.json")

                await db2.commit()
        except Exception as exc:
            logger.warning("train_run.model_register_failed", error=str(exc))

    await enqueue("analyze_run", run_id)
    return {"status": "succeeded", "run_id": run_id, "exit_code": exit_code, "run_root": str(run_root)}
