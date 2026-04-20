"""initial schema — filesystem-native, no MLflow/S3 columns

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="admin"),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts_cols(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("col_count", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("profile_path", sa.String(length=1024), nullable=True),
        sa.Column("profile_summary_json", JSONB(), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_datasets_user_id", "datasets", ["user_id"])

    op.create_table(
        "feature_schemas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("inferred_type", sa.String(length=64), nullable=False),
        sa.Column("semantic_type", sa.String(length=64), nullable=True),
        sa.Column("stats_json", JSONB(), nullable=True),
        sa.Column("missing_pct", sa.Float(), nullable=True),
        sa.Column("unique_count", sa.Integer(), nullable=True),
        *_ts_cols(),
        sa.UniqueConstraint("dataset_id", "column_name", name="uq_feature_schema_dataset_column"),
    )
    op.create_index("ix_feature_schemas_dataset_id", "feature_schemas", ["dataset_id"])

    op.create_table(
        "transform_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_id", sa.String(length=36), sa.ForeignKey("datasets.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("transforms_json", JSONB(), nullable=False),
        sa.Column("split_json", JSONB(), nullable=False),
        sa.Column("sensitive_features", JSONB(), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_transform_configs_dataset_id", "transform_configs", ["dataset_id"])

    op.create_table(
        "model_catalog_entrys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("framework", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("signature_json", JSONB(), nullable=False),
        sa.Column("origin", sa.String(length=64), nullable=False, server_default="builtin"),
        sa.Column("image_uri", sa.String(length=512), nullable=True),
        *_ts_cols(),
        sa.UniqueConstraint("name", name="uq_model_catalog_name"),
    )
    op.create_index("ix_model_catalog_entrys_kind", "model_catalog_entrys", ["kind"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_experiments_user_id", "experiments", ["user_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(length=36),
            sa.ForeignKey("experiments.id"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id", sa.String(length=36), sa.ForeignKey("datasets.id"), nullable=False
        ),
        sa.Column(
            "transform_config_id",
            sa.String(length=36),
            sa.ForeignKey("transform_configs.id"),
            nullable=False,
        ),
        sa.Column(
            "model_catalog_id",
            sa.String(length=36),
            sa.ForeignKey("model_catalog_entrys.id"),
            nullable=False,
        ),
        sa.Column("image_uri", sa.String(length=512), nullable=True),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("hyperparams_json", JSONB(), nullable=False),
        sa.Column("resource_limits_json", JSONB(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_runs_experiment_id", "runs", ["experiment_id"])
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=32), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_metrics_run_id", "metrics", ["run_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("uri", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])

    op.create_table(
        "registered_models",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_ts_cols(),
        sa.UniqueConstraint("name", name="uq_registered_models_name"),
    )

    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "registered_model_id",
            sa.String(length=36),
            sa.ForeignKey("registered_models.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("model_kind", sa.String(length=64), nullable=False, server_default="sklearn"),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("input_schema_json", JSONB(), nullable=False),
        sa.Column("output_schema_json", JSONB(), nullable=False),
        sa.Column("serving_image_uri", sa.String(length=512), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_model_versions_registered_model_id", "model_versions", ["registered_model_id"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "model_version_id",
            sa.String(length=36),
            sa.ForeignKey("model_versions.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column("host_port", sa.Integer(), nullable=True),
        sa.Column("endpoint_url", sa.String(length=512), nullable=True),
        sa.Column("internal_url", sa.String(length=512), nullable=True),
        sa.Column("replicas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("api_key_hash", sa.String(length=255), nullable=True),
        sa.Column("audit_payloads", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
        sa.UniqueConstraint("slug", name="uq_deployments_slug"),
    )
    op.create_index("ix_deployments_model_version_id", "deployments", ["model_version_id"])
    op.create_index("ix_deployments_status", "deployments", ["status"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "deployment_id",
            sa.String(length=36),
            sa.ForeignKey("deployments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="online"),
        sa.Column("input_ref", sa.String(length=1024), nullable=True),
        sa.Column("output_ref", sa.String(length=1024), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("input_preview_json", JSONB(), nullable=True),
        sa.Column("output_preview_json", JSONB(), nullable=True),
    )
    op.create_index(
        "ix_prediction_deployment_received", "predictions", ["deployment_id", "received_at"]
    )

    op.create_table(
        "data_lineages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "upstream_dataset_id",
            sa.String(length=36),
            sa.ForeignKey("datasets.id"),
            nullable=False,
        ),
        sa.Column(
            "downstream_dataset_id",
            sa.String(length=36),
            sa.ForeignKey("datasets.id"),
            nullable=True,
        ),
        sa.Column(
            "transform_config_id",
            sa.String(length=36),
            sa.ForeignKey("transform_configs.id"),
            nullable=True,
        ),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        *_ts_cols(),
    )
    op.create_index("ix_data_lineages_upstream_dataset_id", "data_lineages", ["upstream_dataset_id"])

    op.create_table(
        "bias_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sensitive_feature", sa.String(length=255), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("group_values_json", JSONB(), nullable=False),
        sa.Column("overall_value", sa.Float(), nullable=True),
        sa.Column("report_path", sa.String(length=1024), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_bias_reports_run_id", "bias_reports", ["run_id"])

    op.create_table(
        "explanation_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("feature_importance_json", JSONB(), nullable=True),
        sa.Column("artifact_path", sa.String(length=1024), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_explanation_artifacts_run_id", "explanation_artifacts", ["run_id"])

    op.create_table(
        "build_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("image_id", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("related_id", sa.String(length=36), nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_build_jobs_tag", "build_jobs", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_build_jobs_tag", table_name="build_jobs")
    op.drop_table("build_jobs")
    op.drop_index("ix_explanation_artifacts_run_id", table_name="explanation_artifacts")
    op.drop_table("explanation_artifacts")
    op.drop_index("ix_bias_reports_run_id", table_name="bias_reports")
    op.drop_table("bias_reports")
    op.drop_index("ix_data_lineages_upstream_dataset_id", table_name="data_lineages")
    op.drop_table("data_lineages")
    op.drop_index("ix_prediction_deployment_received", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_index("ix_deployments_model_version_id", table_name="deployments")
    op.drop_table("deployments")
    op.drop_index("ix_model_versions_registered_model_id", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_table("registered_models")
    op.drop_index("ix_artifacts_run_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_metrics_run_id", table_name="metrics")
    op.drop_table("metrics")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_experiment_id", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_experiments_user_id", table_name="experiments")
    op.drop_table("experiments")
    op.drop_index("ix_model_catalog_entrys_kind", table_name="model_catalog_entrys")
    op.drop_table("model_catalog_entrys")
    op.drop_index("ix_transform_configs_dataset_id", table_name="transform_configs")
    op.drop_table("transform_configs")
    op.drop_index("ix_feature_schemas_dataset_id", table_name="feature_schemas")
    op.drop_table("feature_schemas")
    op.drop_index("ix_datasets_user_id", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
