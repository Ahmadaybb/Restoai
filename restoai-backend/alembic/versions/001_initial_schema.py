"""Initial schema: pgvector extension + full table set.

Revision ID: 1ed9a5e04ef0
Revises: (none)
Create Date: 2026-06-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "1ed9a5e04ef0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector extension — idempotent (research.md R9)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_e164", sa.String(20), unique=True, index=True, nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger, unique=True, index=True, nullable=True),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text_value", sa.Text, nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lon", sa.Float, nullable=True),
        sa.Column("area_label", sa.String(80), index=True, nullable=True),
        sa.Column("in_zone", sa.Boolean, default=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "menu_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_translit", sa.String(200), nullable=True),
        sa.Column("description_en", sa.Text, nullable=True),
        sa.Column("description_ar", sa.Text, nullable=True),
        sa.Column("price_usd", sa.Numeric(7, 2), nullable=False),
        sa.Column("available", sa.Boolean, default=True, nullable=False),
        sa.Column("spice_level", sa.String(16), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "menu_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "menu_item_id",
            sa.String(64),
            sa.ForeignKey("menu_items.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.UniqueConstraint("menu_item_id", "language", name="uq_menu_chunk_item_lang"),
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "items_snapshot",
            postgresql.JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("fulfillment", sa.String(16), nullable=False),
        sa.Column("address_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("transcript_url", sa.Text, default="", nullable=False),
        sa.Column("estimated_total_usd", sa.Numeric(7, 2), default=0, nullable=False),
        sa.Column(
            "flags",
            postgresql.JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(32),
            default="awaiting_dispatcher_review",
            index=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatcher_id", sa.String(64), nullable=True),
        sa.Column("entered_in_pos_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("menu_item_id", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
    )

    op.create_table(
        "order_customizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_items.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("awaiting_human", sa.Boolean, default=False, nullable=False),
        sa.Column("assigned_dispatcher_id", sa.String(64), nullable=True),
        sa.Column("active_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("sender", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("intent", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "dispatcher_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("dispatcher_id", sa.String(64), nullable=False),
        sa.Column("dispatcher_name", sa.String(80), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            index=True,
            nullable=False,
        ),
    )

    op.create_table(
        "delivery_zones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("area_name", sa.String(80), unique=True, nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("delivery_zones")
    op.drop_table("dispatcher_actions")
    op.drop_table("conversation_turns")
    op.drop_table("conversations")
    op.drop_table("order_customizations")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("menu_chunks")
    op.drop_table("menu_items")
    op.drop_table("addresses")
    op.drop_table("customers")
    op.execute("DROP EXTENSION IF EXISTS vector")
