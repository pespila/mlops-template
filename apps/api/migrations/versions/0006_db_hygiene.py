"""DB hygiene — User.role default 'member', server_default timestamps,
RESTRICT cascades on parent FKs.

Revision ID: 0006_db_hygiene
Revises: 0005_mv_stage
Create Date: 2026-04-22

Three unrelated P1 items from db.md rolled into one migration:

1. users.role default flips from 'admin' to 'member'. Any bug that
   bypasses seed_admin now produces a non-privileged account, not a
   shadow admin. Pre-existing rows are unchanged — they remain admin.

2. created_at / updated_at gain server_default=func.now(). ORM inserts
   already stamp them; this migration closes the gap for raw SQL,
   data migrations, and psql one-liners.

3. ON DELETE RESTRICT on the parent FKs that routers currently gate
   with 409 (runs.dataset_id, runs.transform_config_id,
   runs.model_catalog_id, model_versions.run_id,
   model_versions.registered_model_id, deployments.model_version_id).
   Previously those were plain ForeignKey without an ondelete policy,
   so a bypassed app guard would silently NULL them out (or fail with
   a bare FK violation depending on dialect). RESTRICT documents the
   intent and keeps behaviour consistent across Postgres + SQLite.

Uses batch_alter_table for SQLite compatibility — SQLite rebuilds the
whole table to change a FK constraint, Postgres does it in place.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_db_hygiene"
down_revision = "0005_mv_stage"
branch_labels = None
depends_on = None


_TIMESTAMP_TABLES: list[str] = [
    "users",
    "datasets",
    "feature_schemas",
    "transform_configs",
    "model_catalog_entrys",
    "experiments",
    "runs",
    "metrics",
    "artifacts",
    "registered_models",
    "model_versions",
    "deployments",
    "data_lineages",
    "bias_reports",
    "explanation_artifacts",
    "model_packages",
    "build_jobs",
]


_FK_RESTRICTS: list[tuple[str, str, str, str, str]] = [
    # (table, constraint_name_or_None, column, referent_table, referent_col)
    ("runs", "runs_dataset_id_fkey", "dataset_id", "datasets", "id"),
    ("runs", "runs_transform_config_id_fkey", "transform_config_id", "transform_configs", "id"),
    (
        "runs",
        "runs_model_catalog_id_fkey",
        "model_catalog_id",
        "model_catalog_entrys",
        "id",
    ),
    ("model_versions", "model_versions_run_id_fkey", "run_id", "runs", "id"),
    (
        "model_versions",
        "model_versions_registered_model_id_fkey",
        "registered_model_id",
        "registered_models",
        "id",
    ),
    (
        "deployments",
        "deployments_model_version_id_fkey",
        "model_version_id",
        "model_versions",
        "id",
    ),
]


def upgrade() -> None:
    # 1. users.role default -> 'member'
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "role",
            existing_type=sa.String(length=32),
            server_default="member",
        )

    # 2. server_default=func.now() on every created_at / updated_at
    for table in _TIMESTAMP_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                existing_nullable=False,
            )
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                existing_nullable=False,
            )

    # 3. FK -> ON DELETE RESTRICT on app-guarded parent references.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, constraint, column, ref_table, ref_col in _FK_RESTRICTS:
            op.drop_constraint(constraint, table, type_="foreignkey")
            op.create_foreign_key(
                constraint,
                source_table=table,
                referent_table=ref_table,
                local_cols=[column],
                remote_cols=[ref_col],
                ondelete="RESTRICT",
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("role", existing_type=sa.String(length=32), server_default="admin")

    for table in _TIMESTAMP_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at", existing_type=sa.DateTime(timezone=True), server_default=None
            )
            batch.alter_column(
                "updated_at", existing_type=sa.DateTime(timezone=True), server_default=None
            )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, constraint, column, ref_table, ref_col in _FK_RESTRICTS:
            op.drop_constraint(constraint, table, type_="foreignkey")
            op.create_foreign_key(
                constraint,
                source_table=table,
                referent_table=ref_table,
                local_cols=[column],
                remote_cols=[ref_col],
            )
