"""HMAC-SHA256 verification for serving-loaded artifacts.

Duplicated intentionally from ``apps/api/aipacken/security/signing.py`` so
this package does not import from the api monorepo (serving_base ships
as a standalone Docker base image). Keep the wire format identical:
``<artifact>.sig`` contains a hex-encoded HMAC-SHA256 over the SHA-256
digest of the artifact's file bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

_CHUNK = 1024 * 1024


class SignatureError(RuntimeError):
    pass


def _secret() -> bytes:
    token = os.environ.get("INTERNAL_HMAC_TOKEN", "").strip()
    if not token:
        raise SignatureError(
            "INTERNAL_HMAC_TOKEN env var is required for artifact verification"
        )
    return token.encode("utf-8")


def _file_digest(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(_CHUNK), b""):
            h.update(chunk)
    return h.digest()


def _sig_path(path: Path) -> Path:
    return path.with_name(path.name + ".sig")


def verify_file(path: Path) -> None:
    path = Path(path)
    if not path.is_file():
        raise SignatureError(f"cannot verify non-file: {path}")
    sig = _sig_path(path)
    if not sig.exists():
        raise SignatureError(f"signature missing: {sig}")
    expected = sig.read_text().strip()
    actual = hmac.new(_secret(), _file_digest(path), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise SignatureError(f"signature mismatch: {path}")
