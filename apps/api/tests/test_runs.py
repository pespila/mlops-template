from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_run_smoke(admin_login: AsyncClient) -> None:
    client = admin_login

    with patch("aipacken.api.routers.datasets.upload_fileobj", return_value="s3://datasets/x"):
        r = await client.post(
            "/api/datasets",
            data={"name": "ds"},
            files={"file": ("a.csv", io.BytesIO(b"a,b,y\n1,2,0\n"), "text/csv")},
        )
    assert r.status_code == 201
    dataset_id = r.json()["id"]

    r = await client.get("/api/catalog/models")
    assert r.status_code == 200
    catalog = r.json()["items"]
    assert catalog, "catalog should be seeded"
    catalog_id = catalog[0]["id"]

    r = await client.post(
        "/api/experiments", json={"name": "exp1", "description": None}
    )
    assert r.status_code == 201
    experiment_id = r.json()["id"]

    # Manually insert a TransformConfig via the admin session's DB.
    from aipacken.db.models import TransformConfig
    from sqlalchemy import select
    from aipacken.db.models import User

    # we can't easily get the session here; post the run directly after inserting
    # a transform config via a small internal helper. For the smoke test we rely
    # on a simpler path: create TransformConfig row through a DB fixture.
    # Instead, we just assert the experiment + dataset + catalog endpoints work;
    # a full run-create requires a TransformConfig FK. Add one via the db fixture.

    import aipacken.db as db_mod

    async with db_mod.SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.role == "admin"))).scalars().first()
        assert admin is not None
        tcfg = TransformConfig(
            dataset_id=dataset_id,
            user_id=admin.id,
            target_column="y",
            transforms_json={},
            split_json={"train": 0.8, "val": 0.1, "test": 0.1},
        )
        db.add(tcfg)
        await db.commit()
        await db.refresh(tcfg)
        tcfg_id = tcfg.id

    r = await client.post(
        "/api/runs",
        json={
            "experiment_id": experiment_id,
            "dataset_id": dataset_id,
            "transform_config_id": tcfg_id,
            "model_catalog_id": catalog_id,
            "hyperparams": {},
            "resource_limits": {},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "queued"
