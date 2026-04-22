"""Pickle-RCE defence: sign + verify round-trip and tamper detection.

security/signing.py is the single gate between a compromised volume and
joblib.load in the serving container (loader.py:63). Zero tests existed
pre-Batch-35b follow-up; this file closes the gap.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _hmac_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_HMAC_TOKEN", "test-secret-xxxxxxxx")


def test_sign_then_verify_ok(tmp_path) -> None:
    from aipacken.security.signing import sign_file, verify_file

    p = tmp_path / "model.pkl"
    p.write_bytes(b"\x80\x04" + os.urandom(1024))
    sign_file(p)
    assert (tmp_path / "model.pkl.sig").exists()
    verify_file(p)  # must not raise


def test_verify_rejects_byte_flip(tmp_path) -> None:
    from aipacken.security.signing import SignatureError, sign_file, verify_file

    p = tmp_path / "model.pkl"
    data = b"\x80\x04" + os.urandom(1024)
    p.write_bytes(data)
    sign_file(p)
    # Flip one byte — signature must no longer match.
    mutated = bytearray(p.read_bytes())
    mutated[10] ^= 0x01
    p.write_bytes(bytes(mutated))
    with pytest.raises(SignatureError):
        verify_file(p)


def test_verify_rejects_missing_sig(tmp_path) -> None:
    from aipacken.security.signing import SignatureError, verify_file

    p = tmp_path / "model.pkl"
    p.write_bytes(b"\x80\x04" + os.urandom(32))
    with pytest.raises(SignatureError):
        verify_file(p)


def test_verify_rejects_wrong_token(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aipacken.security.signing import SignatureError, sign_file, verify_file

    p = tmp_path / "model.pkl"
    p.write_bytes(b"\x80\x04" + os.urandom(64))
    sign_file(p)
    # Rotate the secret; signature becomes unverifiable even though file is intact.
    monkeypatch.setenv("INTERNAL_HMAC_TOKEN", "different-secret-yyyy")
    with pytest.raises(SignatureError):
        verify_file(p)


def test_sign_writes_hex_digest(tmp_path) -> None:
    from aipacken.security.signing import sign_file

    p = tmp_path / "model.pkl"
    p.write_bytes(b"\x80\x04hello")
    sign_file(p)
    sig = (tmp_path / "model.pkl.sig").read_text().strip()
    # SHA-256 hex is 64 chars; defence in depth on the output shape so a
    # future "binary sig" change doesn't silently skip the check.
    assert len(sig) == 64
    int(sig, 16)  # must parse as hex
