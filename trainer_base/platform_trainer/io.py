"""Dataset + artifact I/O over MinIO / S3 and signed HTTP URLs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def _s3_client() -> Any:
    import boto3  # lazy: boto3 import is ~150ms

    endpoint = os.environ.get("S3_ENDPOINT_URL") or None
    return boto3.client("s3", endpoint_url=endpoint)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"not an s3 uri: {uri}")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"malformed s3 uri: {uri}")
    return bucket, key


def download_dataset(uri: str, dest: Path) -> Path:
    """Download from an s3:// URI or a pre-signed HTTP(S) URL to *dest*.

    Returns the final path (may be *dest* itself or *dest* with the remote
    extension preserved when *dest* is a directory).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(uri)

    if parsed.scheme == "s3":
        bucket, key = _parse_s3_uri(uri)
        target = dest if not dest.is_dir() else dest / Path(key).name
        _s3_client().download_file(bucket, key, str(target))
        return target

    if parsed.scheme in ("http", "https"):
        import urllib.request

        remote_name = Path(parsed.path).name or "dataset"
        target = dest if not dest.is_dir() else dest / remote_name
        with urllib.request.urlopen(uri) as resp, open(target, "wb") as fh:  # noqa: S310 — user-supplied signed URL
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        return target

    raise ValueError(f"unsupported dataset uri scheme: {parsed.scheme!r}")


def parse_dataset(path: Path) -> pd.DataFrame:
    """Autodetect csv/tsv/xlsx/parquet/jsonl by suffix."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".tsv", ".txt"):
        return pd.read_csv(path, sep="\t")
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in (".json", ".jsonl", ".ndjson"):
        return pd.read_json(path, lines=suffix != ".json")
    raise ValueError(f"unsupported dataset format: {suffix!r}")


def upload_artifact(local: Path, s3_uri: str) -> None:
    """Upload a single file (not directory) to an s3:// location."""
    bucket, key = _parse_s3_uri(s3_uri)
    if not local.exists() or not local.is_file():
        raise FileNotFoundError(f"artifact not found or not a file: {local}")
    _s3_client().upload_file(str(local), bucket, key)


def read_json_env(name: str) -> Any:
    """Decode a JSON-encoded env var. Empty/unset returns {}."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"env var {name!r} is not valid JSON: {exc}") from exc
