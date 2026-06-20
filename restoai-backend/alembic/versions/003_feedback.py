"""Add order_feedback table — 003-feedback.

Revision ID: 3f7a1b2c9d4e
Revises: 2b4c8d1f9a7e
Create Date: 2026-06-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3f7a1b2c9d4e"
down_revision: str | None = "2b4c8d1f9a7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("star_rating", sa.Integer, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("sentiment", sa.String(10), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "feedback_requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_order_feedback_order_id",
        "order_feedback",
        ["order_id"],
        unique=True,
    )
    op.create_index("ix_order_feedback_customer_id", "order_feedback", ["customer_id"])
    op.create_index("ix_order_feedback_status", "order_feedback", ["status"])
    op.create_index("ix_order_feedback_sentiment", "order_feedback", ["sentiment"])


def downgrade() -> None:
    op.drop_index("ix_order_feedback_sentiment", table_name="order_feedback")
    op.drop_index("ix_order_feedback_status", table_name="order_feedback")
    op.drop_index("ix_order_feedback_customer_id", table_name="order_feedback")
    op.drop_index("ix_order_feedback_order_id", table_name="order_feedback")
    op.drop_table("order_feedback")
