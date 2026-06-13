"""SQLAlchemy ORM — imported ONLY by app/repositories/.

Uses mapped_column() (SQLAlchemy 2.x declarative style). The pgvector
Vector type is used for MenuChunk embeddings (research.md R1, R2).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Customer ──────────────────────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_e164: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="customer")
    orders: Mapped[list["ConfirmedOrder"]] = relationship(back_populates="customer")


# ── Address ───────────────────────────────────────────────────────────────────

class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    text_value: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column()
    lon: Mapped[float | None] = mapped_column()
    area_label: Mapped[str | None] = mapped_column(String(80), index=True)
    in_zone: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="addresses")


# ── MenuItem + MenuChunk ──────────────────────────────────────────────────────

class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str] = mapped_column(String(200))
    name_translit: Mapped[str | None] = mapped_column(String(200))
    description_en: Mapped[str | None] = mapped_column(Text)
    description_ar: Mapped[str | None] = mapped_column(Text)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    spice_level: Mapped[str | None] = mapped_column(String(16))
    tags: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    chunks: Mapped[list["MenuChunk"]] = relationship(back_populates="menu_item")


class MenuChunk(Base):
    __tablename__ = "menu_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    menu_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("menu_items.id"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=True)

    menu_item: Mapped["MenuItem"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("menu_item_id", "language", name="uq_menu_chunk_item_lang"),
    )


# ── ConfirmedOrder + OrderItem + OrderCustomization ───────────────────────────

class ConfirmedOrder(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), index=True
    )
    items_snapshot: Mapped[list[Any]] = mapped_column(JSONB)
    fulfillment: Mapped[str] = mapped_column(String(16))
    address_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    language: Mapped[str] = mapped_column(String(16))
    transcript_url: Mapped[str] = mapped_column(Text, default="")
    estimated_total_usd: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    flags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    state: Mapped[str] = mapped_column(
        String(32), default="awaiting_dispatcher_review", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dispatcher_id: Mapped[str | None] = mapped_column(String(64))
    entered_in_pos_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    dispatcher_actions: Mapped[list["DispatcherAction"]] = relationship(
        back_populates="order"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), index=True
    )
    menu_item_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped["ConfirmedOrder"] = relationship(back_populates="order_items")
    customizations: Mapped[list["OrderCustomization"]] = relationship(
        back_populates="order_item"
    )


class OrderCustomization(Base):
    __tablename__ = "order_customizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order_items.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)

    order_item: Mapped["OrderItem"] = relationship(back_populates="customizations")


# ── Conversation + Turn ───────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    awaiting_human: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_dispatcher_id: Mapped[str | None] = mapped_column(String(64))
    active_draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    turns: Mapped[list["Turn"]] = relationship(back_populates="conversation")


class Turn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), index=True
    )
    sender: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))
    intent: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")


# ── DispatcherAction ──────────────────────────────────────────────────────────

class DispatcherAction(Base):
    __tablename__ = "dispatcher_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True
    )
    dispatcher_id: Mapped[str] = mapped_column(String(64))
    dispatcher_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    order: Mapped["ConfirmedOrder | None"] = relationship(
        back_populates="dispatcher_actions"
    )


# ── DeliveryZone ──────────────────────────────────────────────────────────────

class DeliveryZone(Base):
    __tablename__ = "delivery_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area_name: Mapped[str] = mapped_column(String(80), unique=True)
    aliases: Mapped[list[Any]] = mapped_column(JSONB, default=list)
