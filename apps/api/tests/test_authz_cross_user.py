"""Cross-user authorization (IDOR) regression tests.

The authz chain re-anchored on Run.id after Batch 35b; a join rewrite in
scope_deployment_by_user would silently leak rows across tenants. These
tests seed a resource owned by the admin user, log in as a member, and
assert that GET / PATCH / DELETE all return 404 (never 403, never 200).

404 is load-bearing: returning 403 would leak that the id exists but
isn't owned, giving an enumeration primitive.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


async def _seed_admin_dataset(session_factory: Any, admin_email: str) -> str:
    from sqlalchemy import select

    from aipacken.db.models import Dataset, User

    async with session_factory() as session:
        admin = (await session.execute(select(User).where(User.email == admin_email))).scalar_one()
        ds = Dataset(
            user_id=admin.id,
            name="admin-only",
            source_filename="admin.csv",
            storage_path="datasets/admin-only/raw/admin.csv",
            status="uploaded",
        )
        session.add(ds)
        await session.commit()
        await session.refresh(ds)
        return str(ds.id)


async def _seed_admin_experiment_and_run(session_factory: Any, admin_email: str) -> tuple[str, str]:
    from sqlalchemy import select

    from aipacken.db.models import (
        Dataset,
        Experiment,
        ModelCatalogEntry,
        Run,
        TransformConfig,
        User,
    )

    async with session_factory() as session:
        admin = (await session.execute(select(User).where(User.email == admin_email))).scalar_one()
        ds = Dataset(
            user_id=admin.id,
            name="ds",
            source_filename="ds.csv",
            storage_path="datasets/ds/raw/ds.csv",
            status="uploaded",
        )
        session.add(ds)
        await session.flush()
        tc = TransformConfig(
            dataset_id=ds.id,
            user_id=admin.id,
            target_column="y",
            transforms_json={},
            split_json={},
        )
        session.add(tc)
        # Use any catalog entry — seeded on app startup.
        mc = (await session.execute(select(ModelCatalogEntry).limit(1))).scalar_one()
        exp = Experiment(user_id=admin.id, name="admin-exp")
        session.add(exp)
        await session.flush()
        run = Run(
            experiment_id=exp.id,
            dataset_id=ds.id,
            transform_config_id=tc.id,
            model_catalog_id=mc.id,
            status="succeeded",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        await session.refresh(exp)
        return str(exp.id), str(run.id)


@pytest.mark.asyncio
async def test_member_cannot_read_admin_dataset(
    client: AsyncClient, session_factory: Any, member_client: AsyncClient
) -> None:
    # admin_login is not used — the client fixture arg is the same shared
    # AsyncClient; member_client logs in as the member on top of it so the
    # cookie is the member's. We seed directly through the session factory
    # without going through an admin login.
    dataset_id = await _seed_admin_dataset(session_factory, "admin@local")
    r = await member_client.get(f"/api/datasets/{dataset_id}")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_read_admin_experiment_or_run(
    client: AsyncClient, session_factory: Any, member_client: AsyncClient
) -> None:
    exp_id, run_id = await _seed_admin_experiment_and_run(session_factory, "admin@local")
    r_exp = await member_client.get(f"/api/experiments/{exp_id}")
    r_run = await member_client.get(f"/api/runs/{run_id}")
    assert r_exp.status_code == 404, r_exp.text
    assert r_run.status_code == 404, r_run.text


@pytest.mark.asyncio
async def test_member_cannot_delete_admin_dataset(
    client: AsyncClient, session_factory: Any, member_client: AsyncClient
) -> None:
    dataset_id = await _seed_admin_dataset(session_factory, "admin@local")
    r = await member_client.delete(f"/api/datasets/{dataset_id}")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_member_cannot_patch_admin_dataset(
    client: AsyncClient, session_factory: Any, member_client: AsyncClient
) -> None:
    dataset_id = await _seed_admin_dataset(session_factory, "admin@local")
    r = await member_client.patch(
        f"/api/datasets/{dataset_id}", json={"name": "renamed-by-attacker"}
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_unauth_deployments_list_is_rejected(client: AsyncClient) -> None:
    r = await client.get("/api/deployments")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_unauth_internal_diag_is_rejected(client: AsyncClient) -> None:
    # /api/internal/mlflow/diagnostics used to be unauthenticated; Batch 35b
    # follow-up gates it behind require_admin.
    r = await client.get("/api/internal/mlflow/diagnostics")
    assert r.status_code == 401, r.text
    r2 = await client.get("/api/internal/mlflow/diag/00000000-0000-0000-0000-000000000000")
    assert r2.status_code == 401, r2.text
