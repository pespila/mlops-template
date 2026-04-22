"""MLflow cutover (phase A) — drop the duplicate data tables.

Revision ID: 0007_mlflow_a
Revises: 0006_db_hygiene
Create Date: 2026-04-22

Batches 33-34 got the trainer + api dual-writing to MLflow. This
migration drops the tables whose content is now authoritative in MLflow:

  metrics              -> mlflow run metrics (step-series)
  artifacts            -> mlflow run artifacts
  bias_reports         -> mlflow artifact `reports/bias.json`
  explanation_artifacts-> mlflow artifact `reports/shap.json`

Plus two tables that were dead schema (never populated):
  data_lineages        -> never written; delete
  build_jobs           -> never written; delete

Kept for now (covered by Batch 35b + 36):
  registered_models
  model_versions       (Deployment + ModelPackage still FK here)
  model_packages       (our downloadable-tar feature, not in MLflow)

Rollback story: there is none if you rolled forward and have been
training with MLFLOW_BACKEND=true — MLflow has authoritative metrics
+ artifacts. Pre-cutover data is gone. This is the deliberate
'clean the database, don't keep two things' commit.
"""

from __future__ import annotations

from alembic import op

revision = "0007_mlflow_a"
down_revision = "0006_db_hygiene"
branch_labels = None
depends_on = None


_TABLES_IN_DROP_ORDER: list[str] = [
    # Child tables first (FKs pointing into others).
    "metrics",
    "artifacts",
    "bias_reports",
    "explanation_artifacts",
    "data_lineages",
    "build_jobs",
]


def upgrade() -> None:
    for table in _TABLES_IN_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # Intentional: no downgrade. Re-creating these tables empty would
    # strand any MLflow-only data that arrived since upgrade. If you
    # truly need to roll back, restore from the `make backup` snapshot
    # that preceded the upgrade.
    raise RuntimeError("0007_mlflow_a is forward-only. Restore from backup instead of downgrading.")
