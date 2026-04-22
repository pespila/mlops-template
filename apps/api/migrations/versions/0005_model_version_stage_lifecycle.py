"""model_version stage lifecycle — single-production-per-registered-model

Revision ID: 0005_model_version_stage_lifecycle
Revises: 0004_run_task_hpo_roles
Create Date: 2026-04-22

Before this migration `ModelVersion.stage` was a free-text ``String(32)``
defaulting to ``"none"`` and the trainer hard-coded ``"staging"`` on every
freshly trained version. There was no lifecycle, no rollback primitive,
and nothing stopped two versions of the same registered model from both
carrying stage ``"production"``.

This migration adds a partial unique index that ensures each registered
model has at most one row where ``stage = 'production'``. Postgres honours
partial unique indexes directly; SQLite doesn't, but we only use SQLite
for tests so the constraint is effectively Postgres-only (test-suite
coverage relies on application-level enforcement in the promote endpoint).

Closes mlops.md P0 'No rollback / stage transitions on ModelVersion'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_mv_stage"
down_revision = "0004_run_task_hpo_roles"
branch_labels = None
depends_on = None


_PARTIAL_IX = "ix_model_versions_single_production"


def upgrade() -> None:
    # Partial unique index is Postgres-specific; `postgresql_where` tells
    # Alembic to emit the WHERE clause. On SQLite the connection sees the
    # dialect='sqlite' branch below and skips the index — the promote
    # endpoint enforces the invariant at the app layer for the test DB.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            _PARTIAL_IX,
            "model_versions",
            ["registered_model_id"],
            unique=True,
            postgresql_where=sa.text("stage = 'production'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(_PARTIAL_IX, table_name="model_versions")
