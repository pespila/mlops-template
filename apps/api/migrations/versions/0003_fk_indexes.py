"""FK indexes on frequently-filtered child tables

Revision ID: 0003_fk_indexes
Revises: 0002_model_packages
Create Date: 2026-04-22

Every FK column below is referenced by a router filter or a cascade-delete
query, yet the original schema only indexed a subset of them (most were
declared via ForeignKey(...) alone, which does NOT create a btree index on
Postgres). At non-trivial row counts every list endpoint / cascade delete
falls into a seq scan. Closes db.md P0 "FKs queried by routers have no
index".

SQLite and Postgres both honour CREATE INDEX IF NOT EXISTS, so this is
dialect-safe. The upgrade path is a pure index create — no data motion,
no lock escalation — and downgrade just drops them.
"""

from __future__ import annotations

from alembic import op

revision = "0003_fk_indexes"
down_revision = "0002_model_packages"
branch_labels = None
depends_on = None


_INDEXES: list[tuple[str, str, str]] = [
    # (index_name, table, column)
    ("ix_runs_dataset_id", "runs", "dataset_id"),
    ("ix_runs_transform_config_id", "runs", "transform_config_id"),
    ("ix_runs_model_catalog_id", "runs", "model_catalog_id"),
    ("ix_model_versions_run_id", "model_versions", "run_id"),
    ("ix_deployments_model_version_id", "deployments", "model_version_id"),
    # Partition-hot column for `predictions` list / retention filters.
    ("ix_predictions_received_at", "predictions", "received_at"),
]


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column], if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in _INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
