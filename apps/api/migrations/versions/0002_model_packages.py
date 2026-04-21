"""model_packages — downloadable deployment bundles

Revision ID: 0002_model_packages
Revises: 0001_initial
Create Date: 2026-04-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_model_packages"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "model_version_id",
            sa.String(length=36),
            sa.ForeignKey("model_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("model_packages")
