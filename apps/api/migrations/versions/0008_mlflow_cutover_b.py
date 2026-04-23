"""MLflow cutover (phase B): drop RegisteredModel + ModelVersion.

Snapshot fields on Deployment/ModelPackage.

Revision ID: 0008_mlflow_b
Revises: 0007_mlflow_a
Create Date: 2026-04-22

Batch 35b + 36. Phase A (0007) dropped the tables whose data MLflow
already owned (metrics / artifacts / bias / shap). This phase drops the
local model registry — RegisteredModel + ModelVersion — in favor of
MLflow's built-in Model Registry. Promotion moves to MLflow aliases
(``@staging``, ``@production``) in the same pass.

Deployment + ModelPackage used to FK into ModelVersion. After this:

  * ``run_id`` is a direct FK to Run (for auth + user-scoping).
  * ``mlflow_run_id`` is the MLflow-side run id (for artifact reads).
  * ``registered_model_name`` + ``version_number`` identify the MLflow
    ModelVersion that was active when the deployment / package was
    created.
  * ``model_kind`` / ``storage_path`` / ``input_schema_json`` /
    ``serving_image_uri`` are snapshotted off the old ModelVersion so
    neither the deploy_model nor build_package worker needs to ask MLflow
    every time — and so the serving container keeps loading from its
    existing bind-mount path.

Rollback: forward-only. Pre-cutover Deployment / ModelPackage rows do
not survive the ``DROP COLUMN model_version_id``. Operators who need
the old data must restore from backup (``make backup`` snapshot).
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_mlflow_b"
down_revision = "0007_mlflow_a"
branch_labels = None
depends_on = None

# Safety rails around the destructive DELETEs below. These numbers are
# deliberately low — a prod install is expected to always be empty here
# because Batch 35b landed immediately after 0007. If you're applying
# this against a populated DB, set ``AIPACKEN_ALLOW_DESTRUCTIVE_MIGRATION=1``
# AND take a backup first. See docs/runbooks/MIGRATION-0008.md if present.
_MAX_DELETEROWS_WITHOUT_OPT_IN = 0


_MIGRATION_TABLES = frozenset({"predictions", "deployments", "model_packages"})


def _row_count(conn, table: str) -> int:
    # table is always one of the three names above (called only from
    # _run_destructive_deletes which iterates that literal tuple) — not
    # end-user input. noqa kept as documentation of the deliberate choice.
    if table not in _MIGRATION_TABLES:
        raise ValueError(f"unexpected table name: {table!r}")
    return int(conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)  # noqa: S608


def _run_destructive_deletes() -> None:
    """Delete predictions / deployments / model_packages, with guards.

    This migration is forward-only and the snapshot-column refactor
    can't carry the old rows across — but silently destroying audit
    data (``predictions.input_preview_json`` is PII under
    ``audit_payloads=True``) is an operations footgun. Require explicit
    opt-in via env when the DB is non-empty; fail-loud otherwise.
    """
    conn = op.get_bind()
    counts = {t: _row_count(conn, t) for t in ("predictions", "deployments", "model_packages")}
    total = sum(counts.values())
    opt_in = os.environ.get("AIPACKEN_ALLOW_DESTRUCTIVE_MIGRATION", "").strip() == "1"

    if total > _MAX_DELETEROWS_WITHOUT_OPT_IN and not opt_in:
        raise RuntimeError(
            "0008_mlflow_b would DELETE rows from predictions / deployments / "
            f"model_packages (counts={counts}). Refusing without "
            "AIPACKEN_ALLOW_DESTRUCTIVE_MIGRATION=1. Take a backup first "
            "(see scripts/backup.sh), then retry with the env var set."
        )
    print(f"[0008_mlflow_b] deleting rows: {counts} (opt_in={opt_in})")
    op.execute("DELETE FROM predictions")
    op.execute("DELETE FROM deployments")
    op.execute("DELETE FROM model_packages")


def upgrade() -> None:
    # Deployments: drop the FK into ModelVersion, replace with Run FK +
    # snapshot fields. Pre-cutover rows are destroyed because the
    # snapshot columns can't be populated backwards; see runbook.
    _run_destructive_deletes()

    op.drop_index("ix_deployments_model_version_id", table_name="deployments")
    op.drop_column("deployments", "model_version_id")

    op.add_column(
        "deployments",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False),
    )
    op.add_column("deployments", sa.Column("mlflow_run_id", sa.String(64), nullable=True))
    op.add_column("deployments", sa.Column("registered_model_name", sa.String(255), nullable=True))
    op.add_column("deployments", sa.Column("version_number", sa.Integer, nullable=True))
    op.add_column(
        "deployments",
        sa.Column("model_kind", sa.String(64), nullable=False, server_default="sklearn"),
    )
    op.add_column("deployments", sa.Column("storage_path", sa.String(1024), nullable=True))
    op.add_column("deployments", sa.Column("serving_image_uri", sa.String(512), nullable=True))
    op.add_column(
        "deployments",
        sa.Column(
            "input_schema_json",
            sa.JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    op.create_index("ix_deployments_run_id", "deployments", ["run_id"])
    op.create_index("ix_deployments_mlflow_run_id", "deployments", ["mlflow_run_id"])

    # ModelPackages: same shape, no storage_path on the model side
    # (tar sits at ``ModelPackage.storage_path``, same column as before).
    op.drop_index("ix_model_packages_model_version_id", table_name="model_packages")
    op.drop_column("model_packages", "model_version_id")

    op.add_column(
        "model_packages",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False),
    )
    op.add_column("model_packages", sa.Column("mlflow_run_id", sa.String(64), nullable=True))
    op.add_column(
        "model_packages",
        sa.Column("registered_model_name", sa.String(255), nullable=True),
    )
    op.add_column("model_packages", sa.Column("version_number", sa.Integer, nullable=True))
    op.add_column(
        "model_packages",
        sa.Column("model_kind", sa.String(64), nullable=False, server_default="sklearn"),
    )
    op.add_column(
        "model_packages",
        sa.Column("serving_image_uri", sa.String(512), nullable=True),
    )
    op.add_column(
        "model_packages",
        sa.Column(
            "input_schema_json",
            sa.JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    op.create_index("ix_model_packages_run_id", "model_packages", ["run_id"])
    op.create_index("ix_model_packages_mlflow_run_id", "model_packages", ["mlflow_run_id"])

    # Finally drop the registry tables — MLflow owns them now.
    op.execute("DROP TABLE IF EXISTS model_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS registered_models CASCADE")


def downgrade() -> None:
    raise RuntimeError("0008_mlflow_b is forward-only. Restore from backup if you need to revert.")
