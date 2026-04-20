"""Seed a small demo dataset onto the platform-data volume + Postgres.

Invoked by `make seed`. Creates an iris-like classification dataset in
memory, writes it as CSV under `datasets/demo/raw/train.csv`, and creates
a Dataset row owned by the admin user.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sklearn.datasets import load_iris
from sqlalchemy import select

from aipacken import storage
from aipacken.db import SessionLocal
from aipacken.db.models import Dataset, User

logger = structlog.get_logger(__name__)


async def seed_demo() -> str:
    storage.ensure_base_dirs()

    import pandas as pd

    iris = load_iris(as_frame=True)
    df = iris.frame.rename(columns={"target": "species"})
    df["species"] = df["species"].astype(int)

    dataset_id = "demo"
    raw_path = storage.dataset_raw_path(dataset_id, "train.csv")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw_path, index=False)
    storage_path = storage.to_relative(raw_path)

    async with SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.role == "admin"))).scalars().first()
        if admin is None:
            raise RuntimeError("admin user not seeded — run migrations/startup first")
        existing = (
            await db.execute(select(Dataset).where(Dataset.storage_path == storage_path))
        ).scalars().first()
        if existing is not None:
            logger.info("seed.demo.exists", dataset_id=existing.id)
            return existing.id
        d = Dataset(
            id=str(uuid.uuid4()),
            user_id=admin.id,
            name="demo-iris",
            source_filename="train.csv",
            row_count=int(df.shape[0]),
            col_count=int(df.shape[1]),
            size_bytes=raw_path.stat().st_size,
            storage_path=storage_path,
            status="uploaded",
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
        logger.info("seed.demo.created", dataset_id=d.id)
        return d.id


def main() -> int:
    dataset_id = asyncio.run(seed_demo())
    print(dataset_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
