from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_PLACEHOLDERS = ("change-me", "change_me", "CHANGE-ME", "CHANGEME")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    platform_env: Literal["dev", "prod"] = "dev"
    platform_secret_key: str = Field(..., min_length=32)
    platform_admin_email: str = "admin@local"
    # Dev placeholder — _reject_placeholder_secrets_in_prod below refuses
    # to boot when PLATFORM_ENV=prod and this still carries "change-me*".
    platform_admin_password: str = "change-me"  # noqa: S105

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

    # Dev placeholder — same validator below blocks prod boot if unchanged.
    internal_hmac_token: str = "change-me-internal-hmac-token"  # noqa: S105

    trainer_base_image: str = "platform/trainer-base:latest"
    serving_base_image: str = "platform/serving-base:latest"
    serving_base_autogluon_image: str = "platform/serving-base-autogluon:latest"
    models_network: str = "models-net"

    prediction_retention_days: int = 90

    # MLflow tracking server URI + a kill-switch flag. ``mlflow_backend``
    # defaults True in every supported install — the flag is retained so
    # the api can fail-closed at startup with a clearer error than a deep
    # AttributeError if MLflow is unreachable.
    mlflow_tracking_uri: str = ""
    mlflow_backend: bool = True

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_prod(self) -> "Settings":
        """Fail fast in prod if any secret still carries its placeholder default.

        Prevents silent boot with `PLATFORM_ADMIN_PASSWORD=change-me` or a
        default `INTERNAL_HMAC_TOKEN` — both are ship-stopping defaults and
        an operator rotating the stack should hit the wall, not discover it
        from an incident.
        """
        if self.platform_env != "prod":
            return self

        violations: list[str] = []
        if any(pat in self.platform_admin_password for pat in _WEAK_PLACEHOLDERS):
            violations.append("PLATFORM_ADMIN_PASSWORD")
        if any(pat in self.internal_hmac_token for pat in _WEAK_PLACEHOLDERS):
            violations.append("INTERNAL_HMAC_TOKEN")
        if any(pat in self.platform_secret_key for pat in _WEAK_PLACEHOLDERS):
            violations.append("PLATFORM_SECRET_KEY")

        if violations:
            raise ValueError(
                "Refusing to boot in PLATFORM_ENV=prod with placeholder values for: "
                f"{', '.join(violations)}. Set real secrets in .env before starting."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
