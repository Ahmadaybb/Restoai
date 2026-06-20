"""Add out_for_delivery_at column to orders — 004-order-delivery-state.

Revision ID: 4a8e2c1f6b3d
Revises: 3f7a1b2c9d4e
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a8e2c1f6b3d"
down_revision: str | None = "3f7a1b2c9d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("out_for_delivery_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "out_for_delivery_at")
