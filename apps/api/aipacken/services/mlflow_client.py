"""MLflow client adapter for the FastAPI read paths.

Wraps ``mlflow.MlflowClient`` and shapes its output into the existing
Pydantic response models (``RunRead``, ``MetricRead``, ``ArtifactRead``,
``ExperimentRead``) so the frontend doesn't notice the cutover.

Design
------

* **Lazy singleton.** ``get_client()`` caches a single ``MlflowClient``
  per process. Cheap to call; the underlying client is thread-safe.
* **Flag-gated.** ``mlflow_enabled()`` returns True iff both
  ``mlflow_backend=True`` AND ``mlflow_tracking_uri`` is set. Routers
  branch on this before calling anything here.
* **Platform-id mapping.** Our DB ``Run.id`` is a UUID; MLflow runs have
  their own ids. At training-time the trainer tags each MLflow run with
  ``platform.run_id=<our-uuid>``; ``find_run_by_platform_id()`` searches
  by that tag so FastAPI never has to store the MLflow run id.
* **Never 500.** Every helper returns ``None`` (or an empty list) when
  MLflow is unreachable or the run/experiment is missing. Routers
  convert that into the right HTTP status.

Writers (create experiment, start run) stay in the router + worker for
Batches 32-34; Batch 35 flips the last direct DB writes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from aipacken.config import get_settings

if TYPE_CHECKING:
    from mlflow import MlflowClient  # type: ignore[import-not-found]
    from mlflow.entities import Experiment as MlflowExperiment  # type: ignore[import-not-found]
    from mlflow.entities import Run as MlflowRun  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


def mlflow_enabled() -> bool:
    """True iff MLflow backend is on AND a tracking URI is configured."""
    s = get_settings()
    return bool(s.mlflow_backend and s.mlflow_tracking_uri)


@lru_cache(maxsize=1)
def get_client() -> MlflowClient | None:
    """Return a shared MlflowClient or None when MLflow is disabled."""
    if not mlflow_enabled():
        return None
    try:
        from mlflow import MlflowClient

        return MlflowClient(tracking_uri=get_settings().mlflow_tracking_uri)
    except Exception as exc:
        logger.warning("mlflow.client_init_failed error=%s", exc)
        return None


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


def _experiment_to_read(exp: MlflowExperiment) -> dict[str, Any]:
    """Shape an MlflowExperiment into the ExperimentRead payload."""
    return {
        "id": exp.experiment_id,
        "user_id": exp.tags.get("platform.user_id", ""),
        "name": exp.name,
        "description": exp.tags.get("mlflow.note.content") or None,
        "created_at": _ms_to_dt(exp.creation_time),
        "updated_at": _ms_to_dt(exp.last_update_time or exp.creation_time),
    }


def list_experiments(user_id: str | None = None) -> list[dict[str, Any]]:
    """All experiments visible to the caller. ``user_id=None`` returns every one."""
    client = get_client()
    if client is None:
        return []
    try:
        experiments = client.search_experiments(max_results=500)
    except Exception as exc:
        logger.warning("mlflow.list_experiments_failed error=%s", exc)
        return []
    if user_id is None:
        return [_experiment_to_read(e) for e in experiments]
    return [
        _experiment_to_read(e) for e in experiments if e.tags.get("platform.user_id") == user_id
    ]


def get_experiment_by_name(name: str) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    try:
        exp = client.get_experiment_by_name(name)
    except Exception as exc:
        logger.warning("mlflow.get_experiment_failed name=%s error=%s", name, exc)
        return None
    return _experiment_to_read(exp) if exp else None


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _run_to_read(run: MlflowRun) -> dict[str, Any]:
    """Shape a mlflow Run into the RunRead payload."""
    info = run.info
    data = run.data
    tags = data.tags or {}
    return {
        "id": tags.get("platform.run_id") or info.run_id,
        "experiment_id": info.experiment_id,
        "dataset_id": tags.get("platform.dataset_id", ""),
        "transform_config_id": tags.get("platform.transform_config_id", ""),
        "model_catalog_id": tags.get("platform.model_catalog_id", ""),
        "display_name": info.run_name or None,
        "status": _status_mlflow_to_platform(info.status),
        "hyperparams_json": dict(data.params or {}),
        "resource_limits_json": {},
        "task": tags.get("platform.task"),
        "hpo_json": None,
        "roles_json": None,
        "image_uri": tags.get("platform.trainer_image"),
        "container_id": None,
        "error_message": tags.get("mlflow.log-model.history") if info.status == "FAILED" else None,
        "started_at": _ms_to_dt(info.start_time) if info.start_time else None,
        "finished_at": _ms_to_dt(info.end_time) if info.end_time else None,
        "created_at": _ms_to_dt(info.start_time or info.end_time or 0),
        "updated_at": _ms_to_dt(info.end_time or info.start_time or 0),
    }


def _status_mlflow_to_platform(status: str) -> str:
    # Platform states: queued / running / succeeded / failed / cancelled.
    # MLflow: RUNNING / SCHEDULED / FINISHED / FAILED / KILLED.
    return {
        "SCHEDULED": "queued",
        "RUNNING": "running",
        "FINISHED": "succeeded",
        "FAILED": "failed",
        "KILLED": "cancelled",
    }.get(status, status.lower())


def find_run_by_platform_id(platform_run_id: str) -> MlflowRun | None:
    """Look up an MLflow run by its ``platform.run_id`` tag.

    The tag name contains a dot, which MLflow's filter-string parser
    treats as an identifier separator — so the key must be backtick-
    quoted. Without the backticks ``tags.platform.run_id = 'x'`` is
    parsed as three tokens and every search returns zero runs, which
    is what bit Batch 35e in staging.
    """
    client = get_client()
    if client is None:
        return None
    try:
        results = client.search_runs(
            experiment_ids=[e.experiment_id for e in client.search_experiments(max_results=500)],
            filter_string=f"tags.`platform.run_id` = '{platform_run_id}'",
            max_results=1,
        )
    except Exception as exc:
        logger.warning("mlflow.find_run_failed platform_run_id=%s error=%s", platform_run_id, exc)
        return None
    return results[0] if results else None


def get_run(platform_run_id: str) -> dict[str, Any] | None:
    run = find_run_by_platform_id(platform_run_id)
    return _run_to_read(run) if run else None


def list_runs(experiment_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    client = get_client()
    if client is None:
        return []
    try:
        if experiment_id:
            exps = [experiment_id]
        else:
            exps = [e.experiment_id for e in client.search_experiments(max_results=500)]
        runs = client.search_runs(
            experiment_ids=exps,
            max_results=limit,
            order_by=["attribute.start_time DESC"],
        )
    except Exception as exc:
        logger.warning("mlflow.list_runs_failed error=%s", exc)
        return []
    return [_run_to_read(r) for r in runs]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def get_run_metrics(platform_run_id: str) -> list[dict[str, Any]]:
    """Return every logged metric value for a platform run.

    MLflow exposes history via ``get_metric_history`` per metric name;
    the cumulative dict of metric->latest value is on ``run.data.metrics``.
    For the Metric rows the UI expects (one row per value + step),
    we fan out to get_metric_history over the metrics dict.
    """
    client = get_client()
    if client is None:
        return []
    run = find_run_by_platform_id(platform_run_id)
    if run is None:
        return []
    out: list[dict[str, Any]] = []
    try:
        for name in (run.data.metrics or {}).keys():
            history = client.get_metric_history(run.info.run_id, name)
            for m in history:
                out.append(
                    {
                        "id": f"{run.info.run_id}:{name}:{m.step}:{m.timestamp}",
                        "run_id": platform_run_id,
                        "name": name,
                        "value": float(m.value),
                        "step": int(m.step) if m.step is not None else None,
                        "phase": None,
                        "created_at": _ms_to_dt(m.timestamp),
                        "updated_at": _ms_to_dt(m.timestamp),
                    }
                )
    except Exception as exc:
        logger.warning(
            "mlflow.get_metrics_failed platform_run_id=%s error=%s", platform_run_id, exc
        )
        return []
    return out


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def list_run_artifacts(platform_run_id: str) -> list[dict[str, Any]]:
    """Flatten an MLflow run's artifact tree into Artifact-row payloads."""
    client = get_client()
    if client is None:
        return []
    run = find_run_by_platform_id(platform_run_id)
    if run is None:
        return []

    out: list[dict[str, Any]] = []
    try:
        _walk_artifacts(client, run.info.run_id, "", out, platform_run_id)
    except Exception as exc:
        logger.warning(
            "mlflow.list_artifacts_failed platform_run_id=%s error=%s",
            platform_run_id,
            exc,
        )
        return []
    return out


def _walk_artifacts(
    client: MlflowClient,
    mlflow_run_id: str,
    prefix: str,
    out: list[dict[str, Any]],
    platform_run_id: str,
) -> None:
    for entry in client.list_artifacts(mlflow_run_id, path=prefix or None):
        if entry.is_dir:
            _walk_artifacts(client, mlflow_run_id, entry.path, out, platform_run_id)
            continue
        name = entry.path.rsplit("/", 1)[-1]
        kind, content_type = _classify_artifact(name)
        out.append(
            {
                "id": f"{mlflow_run_id}:{entry.path}",
                "run_id": platform_run_id,
                "kind": kind,
                "name": name,
                "uri": f"mlflow-artifacts:/{mlflow_run_id}/{entry.path}",
                "size_bytes": int(entry.file_size) if entry.file_size else None,
                "content_type": content_type,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )


def read_run_json(platform_run_id: str, artifact_path: str) -> dict[str, Any] | list[Any] | None:
    """Download + json.load a specific artifact from a platform run.

    Returns None when MLflow is disabled, the run isn't found, the
    artifact doesn't exist, or the file isn't valid JSON. Used by the
    routers that serve SHAP / bias / selected_hyperparams straight from
    the MLflow artifact store instead of the DB.
    """
    import json
    import tempfile

    client = get_client()
    if client is None:
        return None
    run = find_run_by_platform_id(platform_run_id)
    if run is None:
        return None
    try:
        import mlflow  # type: ignore[import-not-found]

        local = mlflow.artifacts.download_artifacts(
            run_id=run.info.run_id,
            artifact_path=artifact_path,
            dst_path=tempfile.mkdtemp(prefix="aipacken-read-"),
        )
        with open(local) as fp:
            return json.load(fp)
    except Exception as exc:
        logger.warning(
            "mlflow.read_json_failed platform_run_id=%s path=%s error=%s",
            platform_run_id,
            artifact_path,
            exc,
        )
        return None


def _classify_artifact(name: str) -> tuple[str, str | None]:
    """Mirror the classification rules from jobs/tasks/train_run.py."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_to_dt(ms: int | None) -> datetime:
    """MLflow stores timestamps as epoch milliseconds; we use datetime."""
    if not ms:
        return datetime.now(UTC)
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
