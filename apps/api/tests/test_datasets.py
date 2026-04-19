from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_datasets(admin_login: AsyncClient) -> None:
    client = admin_login
    with patch("aipacken.api.routers.datasets.upload_fileobj", return_value="s3://datasets/x"):
        r = await client.post(
            "/api/datasets",
            data={"name": "test-ds"},
            files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "test-ds"
    dataset_id = body["id"]

    r = await client.get("/api/datasets")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = await client.get(f"/api/datasets/{dataset_id}")
    assert r.status_code == 200
    assert r.json()["id"] == dataset_id
