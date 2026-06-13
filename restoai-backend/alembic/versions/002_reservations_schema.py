"""Add reservations table — 002-reservations.

Revision ID: 2b4c8d1f9a7e
Revises: 1ed9a5e04ef0
Create Date: 2026-06-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2b4c8d1f9a7e"
down_revision: str | None = "1ed9a5e04ef0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(12), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("time", sa.Time(timezone=False), nullable=False),
        sa.Column("party_size", sa.SmallInteger, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("seating_preference", sa.String(24), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_reservations_customer_id", "reservations", ["customer_id"])
    op.create_index("ix_reservations_state", "reservations", ["state"])
    op.create_index("ix_reservations_reference", "reservations", ["reference"])
    op.create_index("ix_reservations_date", "reservations", ["date"])


def downgrade() -> None:
    op.drop_index("ix_reservations_date", table_name="reservations")
    op.drop_index("ix_reservations_reference", table_name="reservations")
    op.drop_index("ix_reservations_state", table_name="reservations")
    op.drop_index("ix_reservations_customer_id", table_name="reservations")
    op.drop_table("reservations")
