"""Make reservations.customer_id nullable for dispatcher-created reservations.

Revision ID: 6c4f1a9e2b8d
Revises: 5b9d3e2f7c1a
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision: str = "6c4f1a9e2b8d"
down_revision: str | None = "5b9d3e2f7c1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("reservations", "customer_id", nullable=True)


def downgrade() -> None:
    op.alter_column("reservations", "customer_id", nullable=False)
