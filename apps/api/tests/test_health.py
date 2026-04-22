import os

os.environ.setdefault("PLATFORM_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient

from aipacken.main import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    r = client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
