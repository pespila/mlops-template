"""HMAC-SHA256 signing for artifacts written + read across trust boundaries.

The trainer container writes model files (``model.pkl``) that are later
unpickled by the serving container and the ``build_package`` worker. A
malicious model file would trigger arbitrary code execution inside those
processes during ``joblib.load`` — the classic pickle-RCE primitive.

Signing each artifact at trainer exit and verifying before load means an
attacker who can write a bad ``model.pkl`` into the shared volume cannot
make the serving container load it (they do not know
``INTERNAL_HMAC_TOKEN``).

Wire format:
  <artifact_name>.sig  contains a single hex-encoded HMAC-SHA256 over the
  SHA-256 digest of the artifact's file bytes. Two-step (file digest,
  then HMAC over that) keeps the HMAC work constant regardless of file
  size; the file digest already captures every byte.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

_CHUNK = 1024 * 1024


class SignatureError(RuntimeError):
    """Raised when an artifact signature is missing or does not verify."""


def _secret() -> bytes:
    token = os.environ.get("INTERNAL_HMAC_TOKEN", "").strip()
    if not token:
        raise SignatureError(
            "INTERNAL_HMAC_TOKEN env var is required for artifact signing"
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


def sign_file(path: Path) -> Path:
    """Write ``<path>.sig`` containing the HMAC of the artifact's digest.

    Overwrites any existing signature. Returns the signature file path.
    """
    path = Path(path)
    if not path.is_file():
        raise SignatureError(f"cannot sign non-file: {path}")
    tag = hmac.new(_secret(), _file_digest(path), hashlib.sha256).hexdigest()
    sig = _sig_path(path)
    sig.write_text(tag + "\n")
    return sig


def verify_file(path: Path) -> None:
    """Verify ``<path>.sig``. Raises ``SignatureError`` on missing or mismatched sig.

    Uses constant-time compare to avoid timing attacks on the hex tag.
    """
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
