"""MLflow dual-write sink for the trainer.

Batch 33 of the MLflow migration. The trainer still writes the existing
JSONL / DB-backed artifacts unchanged; this sink additionally forwards
every log_metric / log_param / log_artifact call to the MLflow Tracking
Server so Batches 34+ can read from MLflow as the source of truth.

Design goals:

* **Graceful degradation.** If MLFLOW_TRACKING_URI is unset or the
  tracking server is unreachable, every function below logs a warning
  and returns without raising. The trainer continues to produce the
  JSONL + DB-backed outputs exactly as before.
* **One run per training container.** ``begin()`` creates / resumes a
  single MLflow run keyed on the platform RUN_ID; ``end()`` closes it.
  All log_* calls in between attach to it.
* **No hidden dependencies.** Nothing in this module imports from the
  rest of the trainer — it is pure MLflow + stdlib so it can be
  imported from any entry point (supervised pipeline, clustering,
  forecasting, recommender) without pulling sklearn / pandas eagerly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("platform_trainer.mlflow_sink")

# Module-level guard: once a single log_* call fails, we stop retrying
# within this container run so the trainer does not spend wall-clock
# time reconnecting to an unreachable tracking server for every metric.
_DISABLED: bool = False


def _enabled() -> bool:
    return bool(os.environ.get("MLFLOW_TRACKING_URI", "").strip()) and not _DISABLED


def _disable(reason: str) -> None:
    global _DISABLED
    if not _DISABLED:
        logger.warning("mlflow.disabled reason=%s", reason)
        _DISABLED = True


def _mlflow():  # type: ignore[no-untyped-def]
    """Lazy import so a trainer container without mlflow installed does not crash."""
    try:
        import mlflow  # type: ignore[import-not-found]

        return mlflow
    except ImportError as exc:
        _disable(f"import_failed:{exc}")
        return None


def begin(
    run_id: str, experiment_name: str, tags: dict[str, str] | None = None
) -> str | None:
    """Start an MLflow run tied to the platform run_id.

    Returns the MLflow run id on success, None when disabled.

    Experiment handling is explicit:
      * if an experiment with ``experiment_name`` already exists, use it;
      * otherwise create it with ``artifact_location='mlflow-artifacts:/'``
        so the server's proxied-artifact mode is used.

    That explicit artifact_location matters because ``set_experiment``
    creates-on-demand with whatever ``--default-artifact-root`` the
    tracking server was booted with. If the server flipped between
    ``s3://...`` and ``mlflow-artifacts:/`` across deploys, pre-existing
    experiments keep their original location and clients hit the wrong
    endpoint. Setting it explicitly here removes that drift.
    """
    if not _enabled():
        return None
    mlflow = _mlflow()
    if mlflow is None:
        return None
    try:
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        from mlflow import MlflowClient  # type: ignore[import-not-found]

        client = MlflowClient()
        exp = client.get_experiment_by_name(experiment_name)
        if exp is None:
            client.create_experiment(
                name=experiment_name,
                artifact_location="mlflow-artifacts:/",
            )
        # set_experiment here is a no-op for routing; we call it so
        # mlflow's process-wide active-experiment state is primed.
        mlflow.set_experiment(experiment_name)
        active = mlflow.start_run(
            run_name=run_id,
            tags={"platform.run_id": run_id, **(tags or {})},
        )
        logger.info(
            "mlflow.started platform_run_id=%s mlflow_run_id=%s",
            run_id,
            active.info.run_id,
        )
        return str(active.info.run_id)
    except Exception as exc:  # noqa: BLE001 — telemetry must never crash the trainer
        _disable(f"start_failed:{exc}")
        return None


def log_params(params: dict[str, Any]) -> None:
    if not _enabled() or not params:
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        # MLflow caps param values at 6000 chars; coerce everything to
        # str first and truncate oversized values rather than raising.
        safe = {k: str(v)[:5999] for k, v in params.items()}
        mlflow.log_params(safe)
    except Exception as exc:  # noqa: BLE001
        _disable(f"log_params_failed:{exc}")


def log_metric(name: str, value: float, step: int | None = None) -> None:
    if not _enabled():
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        mlflow.log_metric(name, float(value), step=step)
    except Exception as exc:  # noqa: BLE001
        _disable(f"log_metric_failed:{exc}")


def log_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    if not _enabled() or not metrics:
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()}, step=step)
    except Exception as exc:  # noqa: BLE001
        _disable(f"log_metrics_failed:{exc}")


def log_artifact(local_path: str | Path, artifact_path: str | None = None) -> None:
    """Upload a file (or directory) to MLflow's configured artifact store."""
    if not _enabled():
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        p = Path(local_path)
        if not p.exists():
            return
        if p.is_dir():
            mlflow.log_artifacts(str(p), artifact_path=artifact_path)
        else:
            mlflow.log_artifact(str(p), artifact_path=artifact_path)
    except Exception as exc:  # noqa: BLE001
        _disable(f"log_artifact_failed:{exc}")


def set_tag(key: str, value: str) -> None:
    if not _enabled():
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        mlflow.set_tag(key, value)
    except Exception as exc:  # noqa: BLE001
        _disable(f"set_tag_failed:{exc}")


def end(status: str = "FINISHED") -> None:
    """Close the active MLflow run. Safe to call when no run is active."""
    if not _enabled():
        return
    mlflow = _mlflow()
    if mlflow is None:
        return
    try:
        mlflow.end_run(status=status)
    except Exception as exc:  # noqa: BLE001
        _disable(f"end_failed:{exc}")
