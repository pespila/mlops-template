from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_me_logout(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me")
    assert r.status_code == 401

    r = await client.post("/api/auth/login", json={"email": "admin@local", "password": "change-me"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "admin@local"
    assert body["role"] == "admin"

    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "admin@local"

    r = await client.post("/api/auth/logout")
    assert r.status_code == 204

    r = await client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient) -> None:
    r = await client.post("/api/auth/login", json={"email": "admin@local", "password": "nope"})
    assert r.status_code == 401
