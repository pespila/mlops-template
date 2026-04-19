"""Seed a small demo dataset into MinIO + Postgres.

Invoked by `make seed`. Creates an iris-like classification dataset in
memory, uploads it as CSV to MinIO `datasets/demo/train.csv`, and creates
a Dataset row owned by the admin user.
"""

from __future__ import annotations

import asyncio
import io
import uuid

import structlog
from sklearn.datasets import load_iris
from sqlalchemy import select

from aipacken.config import get_settings
from aipacken.db import SessionLocal
from aipacken.db.models import Dataset, User
from aipacken.services.minio_client import ensure_buckets, upload_fileobj

logger = structlog.get_logger(__name__)


async def seed_demo() -> str:
    settings = get_settings()
    ensure_buckets()

    import pandas as pd

    iris = load_iris(as_frame=True)
    df = iris.frame.rename(columns={"target": "species"})
    df["species"] = df["species"].astype(int)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    key = "demo/train.csv"
    upload_fileobj(
        io.BytesIO(csv_bytes),
        bucket=settings.s3_bucket_datasets,
        key=key,
        content_type="text/csv",
    )
    storage_uri = f"s3://{settings.s3_bucket_datasets}/{key}"

    async with SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.role == "admin"))).scalars().first()
        if admin is None:
            raise RuntimeError("admin user not seeded — run migrations/startup first")
        existing = (
            await db.execute(select(Dataset).where(Dataset.storage_uri == storage_uri))
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
            storage_uri=storage_uri,
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
