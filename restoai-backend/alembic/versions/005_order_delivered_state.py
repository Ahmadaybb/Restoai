"""Add delivered_at column to orders — 005-order-delivered-state.

Revision ID: 5b9d3e2f7c1a
Revises: 4a8e2c1f6b3d
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b9d3e2f7c1a"
down_revision: str | None = "4a8e2c1f6b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivered_at")
