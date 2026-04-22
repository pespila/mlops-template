from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aipacken.db.base import Base, IdMixin, TimestampsMixin

# Portable JSON column type: JSONB on Postgres (GIN-indexable, compact
# binary), plain JSON on SQLite (test-only). Having one definition keeps
# the test env from needing the JSONB → JSON monkey-patch that lived in
# tests/conftest.py.
JsonColumn = JSON().with_variant(JSONB, "postgresql")


class User(Base, IdMixin, TimestampsMixin):
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Dataset(Base, IdMixin, TimestampsMixin):
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    profile_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    profile_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)


class FeatureSchema(Base, IdMixin, TimestampsMixin):
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    missing_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    unique_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("dataset_id", "column_name", name="uq_feature_schema_dataset_column"),
    )


class TransformConfig(Base, IdMixin, TimestampsMixin):
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    transforms_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    split_json: Mapped[dict[str, Any]] = mapped_column(JsonColumn, nullable=False, default=dict)
    sensitive_features: Mapped[list[str] | None] = mapped_column(JsonColumn, nullable=True)


class ModelCatalogEntry(Base, IdMixin, TimestampsMixin):
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_json: Mapped[dict[str, Any]] = mapped_column(JsonColumn, nullable=False, default=dict)
    origin: Mapped[str] = mapped_column(String(64), default="builtin", nullable=False)
    image_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Experiment(Base, IdMixin, TimestampsMixin):
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Run(Base, IdMixin, TimestampsMixin):
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    transform_config_id: Mapped[str] = mapped_column(
        ForeignKey("transform_configs.id"), nullable=False
    )
    model_catalog_id: Mapped[str] = mapped_column(
        ForeignKey("model_catalog_entrys.id"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    hyperparams_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    resource_limits_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Metric(Base, IdMixin, TimestampsMixin):
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Artifact(Base, IdMixin, TimestampsMixin):
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Relative path inside /var/platform-data (e.g. `runs/{id}/artifacts/model.pkl`).
    # Column is named `uri` for backwards-compat with existing code paths that
    # read `.uri`; conceptually it's a `storage_path`.
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)


class RegisteredModel(Base, IdMixin, TimestampsMixin):
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="registered_model", cascade="all, delete-orphan"
    )


class ModelVersion(Base, IdMixin, TimestampsMixin):
    registered_model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    model_kind: Mapped[str] = mapped_column(String(64), default="sklearn", nullable=False)
    # Relative path inside /var/platform-data (e.g. `models/{mv_id}/model.pkl`
    # for sklearn-flavored models, or `models/{mv_id}/` directory for AutoGluon).
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    input_schema_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    output_schema_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    serving_image_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)

    registered_model: Mapped[RegisteredModel] = relationship(back_populates="versions")


class Deployment(Base, IdMixin, TimestampsMixin):
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    internal_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    replicas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audit_payloads: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Prediction(Base, IdMixin):
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="online", nullable=False)
    input_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_preview_json: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    output_preview_json: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)

    __table_args__ = (Index("ix_prediction_deployment_received", "deployment_id", "received_at"),)


class DataLineage(Base, IdMixin, TimestampsMixin):
    upstream_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id"), nullable=False, index=True
    )
    downstream_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True
    )
    transform_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("transform_configs.id"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)


class BiasReport(Base, IdMixin, TimestampsMixin):
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sensitive_feature: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    group_values_json: Mapped[dict[str, Any]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )
    overall_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class ExplanationArtifact(Base, IdMixin, TimestampsMixin):
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_importance_json: Mapped[dict[str, Any] | None] = mapped_column(
        JsonColumn, nullable=True
    )
    artifact_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class ModelPackage(Base, IdMixin, TimestampsMixin):
    """A downloadable bundle for a ModelVersion.

    Populated asynchronously by the ``build_package`` worker job: bundles the
    serving docker image (``docker save``), the model artifacts, a README,
    a minimal Dockerfile to rebuild the image, and a standalone ``predict.py``
    into a tar.gz living under ``packages/{id}.tar.gz`` on platform-data.
    """

    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuildJob(Base, IdMixin, TimestampsMixin):
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    tag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    image_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
