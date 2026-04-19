from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    platform_env: Literal["dev", "prod"] = "dev"
    platform_secret_key: str = Field(..., min_length=32)
    platform_admin_email: str = "admin@local"
    platform_admin_password: str = "change-me"

    database_url: str = "postgresql+psycopg://platform:platform@postgres:5432/platform"
    redis_url: str = "redis://redis:6379/0"

    s3_endpoint_url: str = "http://minio:9000"
    s3_region: str = "us-east-1"
    minio_root_user: str = "platform"
    minio_root_password: str = "platform-minio"

    s3_bucket_datasets: str = "datasets"
    s3_bucket_artifacts: str = "artifacts"
    s3_bucket_mlflow: str = "mlflow-artifacts"
    s3_bucket_reports: str = "reports"
    s3_bucket_predictions: str = "predictions"

    mlflow_tracking_uri: str = "http://mlflow:5000"
    builder_url: str = "http://builder:8080"

    training_default_cpu: int = 4
    training_default_memory_gb: int = 8
    training_job_timeout_seconds: int = 7200

    session_cookie_name: str = "platform_session"
    session_max_age_seconds: int = 86400


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
