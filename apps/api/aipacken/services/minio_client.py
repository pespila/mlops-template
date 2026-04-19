from __future__ import annotations

from functools import lru_cache
from typing import IO, Any

import boto3
import structlog
from botocore.client import Config

from aipacken.config import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def get_s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_buckets() -> None:
    settings = get_settings()
    s3 = get_s3_client()
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    targets = [
        settings.s3_bucket_datasets,
        settings.s3_bucket_artifacts,
        settings.s3_bucket_mlflow,
        settings.s3_bucket_reports,
        settings.s3_bucket_predictions,
    ]
    for name in targets:
        if name not in existing:
            s3.create_bucket(Bucket=name)
            logger.info("minio.bucket.created", bucket=name)


def upload_fileobj(
    fileobj: IO[bytes], bucket: str, key: str, content_type: str | None = None
) -> str:
    extra = {"ContentType": content_type} if content_type else None
    get_s3_client().upload_fileobj(fileobj, bucket, key, ExtraArgs=extra)
    return f"s3://{bucket}/{key}"


def download_fileobj(bucket: str, key: str, fileobj: IO[bytes]) -> None:
    get_s3_client().download_fileobj(bucket, key, fileobj)


def presign_get(bucket: str, key: str, expires_in: int = 3600) -> str:
    return get_s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
    )


def presign_put(bucket: str, key: str, expires_in: int = 3600) -> str:
    return get_s3_client().generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
    )
