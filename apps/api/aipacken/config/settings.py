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

    # Single named Docker volume for everything the platform produces.
    data_root: str = "/var/platform-data"

    builder_url: str = "http://builder:8080"

    training_default_cpu: int = 4
    training_default_memory_gb: int = 8
    training_job_timeout_seconds: int = 7200

    session_cookie_name: str = "platform_session"
    session_max_age_seconds: int = 86400

    internal_hmac_token: str = "change-me-internal-hmac-token"

    trainer_base_image: str = "platform/trainer-base:latest"
    serving_base_image: str = "platform/serving-base:latest"
    serving_base_autogluon_image: str = "platform/serving-base-autogluon:latest"
    models_network: str = "models-net"

    prediction_retention_days: int = 90
    artifact_retention_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
