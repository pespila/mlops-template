"""runs.task / hpo_json / roles_json — promote reserved-key smuggling

Revision ID: 0004_run_task_hpo_roles
Revises: 0003_fk_indexes
Create Date: 2026-04-22

Before this migration, the router stuffed three semantically-distinct
payloads under reserved keys inside Run.hyperparams_json:
``_task`` (the supervised-task kind), ``_hpo`` (the Optuna config),
``_roles`` (the forecasting / recommender / clustering role map).

The reserved-key trick let us ship without a migration. It also meant:
  * the API contract and the trainer contract were coupled through a
    stringly-typed JSON path with no schema,
  * a real hyperparameter literally named ``_task`` would collide and
    silently break runs,
  * downstream consumers (UI, exports) had to know the smuggling
    convention.

This migration adds real columns. The router and worker now use them;
the reserved-key unpacking path is kept as a backward-compat fallback
for runs that predate this migration, and the router stops writing
the reserved keys going forward.

Closes arch.md P0 'Worker ↔ trainer coupling via stringly-typed JSON'
+ quality.md P1 'Reserved-key smuggling via hyperparams_json'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_run_task_hpo_roles"
down_revision = "0003_fk_indexes"
branch_labels = None
depends_on = None

# Matches db.models.JsonColumn: JSONB on Postgres, plain JSON on SQLite.
_JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("task", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("hpo_json", _JSON_TYPE, nullable=True))
        batch.add_column(sa.Column("roles_json", _JSON_TYPE, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("roles_json")
        batch.drop_column("hpo_json")
        batch.drop_column("task")
