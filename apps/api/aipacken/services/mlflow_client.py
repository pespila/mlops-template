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

Writers (create experiment / run, create model versions, set aliases)
land here too post-cutover: train_run.py calls into this module when
it registers a new MLflow ModelVersion on training success, and the
``/api/models/{id}/versions/{vid}/promote`` endpoint writes aliases
through :func:`set_alias`.
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


def download_run_artifacts(
    platform_run_id: str,
    dst_dir: str,
    artifact_path: str | None = None,
) -> str | None:
    """Pull an artifact (or the whole artifact tree) down to a local dir.

    Used by deploy_model / build_package to stage the trained model on
    ``/var/platform-data`` before handing it to the serving container.
    Returns the local path MLflow wrote to, or None on failure.

    Path-traversal defence: MLflow's HTTP / proxied-artifact repository
    joins ``artifact_path`` segments without strict sanitization on
    older versions (CVE-2023-1177 class). After the download, we walk
    the result tree and reject any file that doesn't resolve under
    ``dst_dir`` — a malicious trainer that logged an artifact named
    ``../../etc/…`` would otherwise drop files outside the deployment's
    staging area (the pickle signature gates load, not cross-drop).
    """
    import shutil as _shutil
    from pathlib import Path as _Path

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
            dst_path=dst_dir,
        )
    except Exception as exc:
        logger.warning(
            "mlflow.download_artifacts_failed platform_run_id=%s error=%s",
            platform_run_id,
            exc,
        )
        return None

    dst_real = _Path(dst_dir).resolve()
    try:
        local_real = _Path(local).resolve()
        if not _path_is_under(local_real, dst_real):
            raise RuntimeError(f"artifact landed outside dst_dir: {local_real}")
        # Walk the tree — symlinks + nested entries both — and assert
        # every path resolves back under dst_dir.
        if local_real.is_dir():
            for child in local_real.rglob("*"):
                if not _path_is_under(child.resolve(), dst_real):
                    raise RuntimeError(f"traversal: {child} escapes {dst_real}")
    except Exception as exc:
        logger.warning(
            "mlflow.download_artifacts_traversal_rejected platform_run_id=%s error=%s",
            platform_run_id,
            exc,
        )
        try:
            _shutil.rmtree(local, ignore_errors=True)
        except OSError as cleanup_exc:
            logger.info("mlflow.download_cleanup_failed error=%s", cleanup_exc)
        return None
    return local


def _path_is_under(candidate, root) -> bool:
    """True iff *candidate* is *root* itself or a descendant of it."""
    from pathlib import Path as _Path

    c = _Path(candidate).resolve()
    r = _Path(root).resolve()
    try:
        c.relative_to(r)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Model registry (Batch 35b)
# ---------------------------------------------------------------------------


def ensure_registered_model(name: str, description: str | None = None) -> None:
    """Create an MLflow RegisteredModel if it doesn't already exist."""
    client = get_client()
    if client is None:
        return
    try:
        client.get_registered_model(name)
    except Exception:
        try:
            client.create_registered_model(name=name, description=description)
        except Exception as exc:
            logger.warning("mlflow.create_registered_model_failed name=%s error=%s", name, exc)


def register_model_version(
    name: str,
    source_uri: str,
    run_id: str,
    description: str | None = None,
    tags: dict[str, str] | None = None,
) -> Any | None:
    """Create a new MLflow ModelVersion under ``name`` pointing at ``source_uri``.

    ``run_id`` is the MLflow run id (not the platform UUID). Returns the
    created ModelVersion (with ``.version`` int) or None on failure.
    """
    client = get_client()
    if client is None:
        return None
    ensure_registered_model(name)
    try:
        return client.create_model_version(
            name=name,
            source=source_uri,
            run_id=run_id,
            description=description,
            tags=tags or {},
        )
    except Exception as exc:
        logger.warning("mlflow.create_model_version_failed name=%s error=%s", name, exc)
        return None


def set_alias(name: str, alias: str, version: int | str) -> bool:
    """Point ``@alias`` on the registered model ``name`` at ``version``.

    Aliases are unique per registered model — setting ``@production`` on
    a new version automatically detaches it from whichever version held
    it before. That's the MLflow-native replacement for the "only one
    production version at a time" invariant the old ``stage`` column
    enforced via a partial unique index.
    """
    client = get_client()
    if client is None:
        return False
    try:
        client.set_registered_model_alias(name=name, alias=alias, version=str(version))
        return True
    except Exception as exc:
        logger.warning("mlflow.set_alias_failed name=%s alias=%s error=%s", name, alias, exc)
        return False


def delete_alias(name: str, alias: str) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        client.delete_registered_model_alias(name=name, alias=alias)
        return True
    except Exception as exc:
        logger.warning("mlflow.delete_alias_failed name=%s alias=%s error=%s", name, alias, exc)
        return False


def list_registered_models(max_results: int = 500) -> list[Any]:
    client = get_client()
    if client is None:
        return []
    try:
        return list(client.search_registered_models(max_results=max_results))
    except Exception as exc:
        logger.warning("mlflow.list_registered_models_failed error=%s", exc)
        return []


def get_registered_model(name: str) -> Any | None:
    client = get_client()
    if client is None:
        return None
    try:
        return client.get_registered_model(name)
    except Exception:
        return None


_REGISTERED_MODEL_NAME_BAD_CHARS = frozenset("'\"\\\n\r\x00`;")


def _assert_safe_model_name(name: str) -> None:
    """Reject registered-model names that would break the MLflow filter.

    MLflow's filter-string parser treats ``'`` and backslash as quote
    delimiters; a name containing either breaks the ``name='<name>'``
    filter and can broaden the match ("filter-string injection"). The
    trainer only ever mints names of the shape ``{catalog}-run-{8hex}``
    so the real attack surface is the admin rename endpoint. We also
    reject control characters and semicolons out of caution.
    """
    if not name or any(ch in _REGISTERED_MODEL_NAME_BAD_CHARS for ch in name):
        raise ValueError(f"unsafe registered-model name: {name!r}")


def search_model_versions(name: str) -> list[Any]:
    """All MLflow ModelVersions belonging to ``name``, newest first.

    The name is validated and single-quote-escaped before being
    interpolated into the filter string — MLflow's filter parser is
    not SQL but ``name='<name>'`` still lets a stray ``'`` broaden
    the match. See _assert_safe_model_name above.
    """
    client = get_client()
    if client is None:
        return []
    try:
        _assert_safe_model_name(name)
    except ValueError as exc:
        logger.warning("mlflow.search_model_versions_rejected error=%s", exc)
        return []
    try:
        rows = client.search_model_versions(f"name='{name}'")
        return sorted(rows, key=lambda r: int(r.version), reverse=True)
    except Exception as exc:
        logger.warning("mlflow.search_model_versions_failed name=%s error=%s", name, exc)
        return []


def get_model_version(name: str, version: int | str) -> Any | None:
    client = get_client()
    if client is None:
        return None
    try:
        return client.get_model_version(name=name, version=str(version))
    except Exception:
        return None


def get_version_by_alias(name: str, alias: str) -> Any | None:
    client = get_client()
    if client is None:
        return None
    try:
        return client.get_model_version_by_alias(name=name, alias=alias)
    except Exception:
        return None


def aliases_for_version(name: str, version: int | str) -> list[str]:
    """Every alias currently pointing at ``(name, version)``.

    MLflow stores aliases as a dict on the RegisteredModel; this walks
    it to find any alias assigned to the given version so the UI can
    render them next to the version row.
    """
    rm = get_registered_model(name)
    if rm is None:
        return []
    version_s = str(version)
    out: list[str] = []
    aliases = getattr(rm, "aliases", None) or {}
    # MLflow exposes aliases as a dict-like {alias_name: version_str}
    if hasattr(aliases, "items"):
        for alias_name, v in aliases.items():
            if str(v) == version_s:
                out.append(str(alias_name))
    else:
        for item in aliases:
            if hasattr(item, "alias") and str(getattr(item, "version", "")) == version_s:
                out.append(str(item.alias))
    return out


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
