"""Filesystem layout helpers for the platform-data volume.

Every path the backend, worker, trainer, or serving container produces lives
under `settings.data_root` (default `/var/platform-data`) and is reachable
through these helpers. No S3, no presigned URLs, no tracking server in the
loop.
"""

from __future__ import annotations

from pathlib import Path

from aipacken.config import get_settings


def _root() -> Path:
    return Path(get_settings().data_root)


def ensure_base_dirs() -> None:
    """Create the top-level layout once at startup.

    The platform-data volume is shared between the api/worker (running as
    root inside the container) and the trainer containers (running as uid
    10001). We relax permissions here so the trainer can write into its
    per-run subdirectory without a chown round-trip.
    """
    import os as _os

    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        _os.chmod(root, 0o777)
    except OSError:
        pass
    for sub in ("datasets", "runs", "models"):
        p = root / sub
        p.mkdir(parents=True, exist_ok=True)
        try:
            _os.chmod(p, 0o777)
        except OSError:
            pass


# ---- dataset ----

def dataset_dir(dataset_id: str) -> Path:
    return _root() / "datasets" / dataset_id


def dataset_raw_dir(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "raw"


def dataset_raw_path(dataset_id: str, filename: str) -> Path:
    return dataset_raw_dir(dataset_id) / filename


def dataset_profile_path(dataset_id: str) -> Path:
    return dataset_dir(dataset_id) / "profile.json"


# ---- run ----

def run_dir(run_id: str) -> Path:
    return _root() / "runs" / run_id


def run_artifacts_dir(run_id: str) -> Path:
    return run_dir(run_id) / "artifacts"


def run_reports_dir(run_id: str) -> Path:
    return run_dir(run_id) / "reports"


def run_metrics_path(run_id: str) -> Path:
    return run_dir(run_id) / "metrics.jsonl"


def run_logs_path(run_id: str) -> Path:
    return run_dir(run_id) / "logs.jsonl"


def ensure_run_dirs(run_id: str) -> None:
    import os as _os

    for p in (run_dir(run_id), run_artifacts_dir(run_id), run_reports_dir(run_id)):
        p.mkdir(parents=True, exist_ok=True)
        try:
            _os.chmod(p, 0o777)
        except OSError:
            pass


# ---- model ----

def model_version_dir(model_version_id: str) -> Path:
    return _root() / "models" / model_version_id


# ---- generic ----

def to_absolute(storage_path: str) -> Path:
    """Resolve a stored relative path (e.g. `runs/{id}/artifacts/model.pkl`) to disk."""
    p = Path(storage_path)
    if p.is_absolute():
        # Keep absolute paths inside the data_root; reject escapes.
        rooted = Path(get_settings().data_root).resolve()
        resolved = p.resolve()
        resolved.relative_to(rooted)  # raises ValueError if outside
        return resolved
    return (_root() / p).resolve()


def to_relative(absolute_path: Path) -> str:
    """Turn an in-volume absolute path into a stored relative path."""
    return str(absolute_path.relative_to(_root()))
