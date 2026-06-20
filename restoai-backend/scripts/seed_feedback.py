"""Seed mock feedback records for UI development/testing.

Usage (from restoai-backend directory):
  # Locally:
  .venv/Scripts/python.exe scripts/seed_feedback.py

  # In Docker:
  docker compose exec api python scripts/seed_feedback.py
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = None  # auto-detected from .env / environment


def _get_db_url() -> str:
    import os
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Try .env file
    env_path = __file__
    for _ in range(3):
        env_path = os.path.dirname(env_path)
    env_file = os.path.join(env_path, ".env")
    if os.path.exists(env_file):
        for line in open(env_file):
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1]
    raise RuntimeError("DATABASE_URL not found in environment or .env")


MOCK_CUSTOMERS = [
    {"id": "aaaaaaaa-0000-0000-0000-000000000001", "display_name": "Layla Hassan",   "phone_e164": "+96170111001", "telegram_user_id": None},
    {"id": "aaaaaaaa-0000-0000-0000-000000000002", "display_name": "Omar Khalil",    "phone_e164": "+96170111002", "telegram_user_id": None},
    {"id": "aaaaaaaa-0000-0000-0000-000000000003", "display_name": "Sara Mansour",   "phone_e164": "+96170111003", "telegram_user_id": None},
    {"id": "aaaaaaaa-0000-0000-0000-000000000004", "display_name": "Karim Abboud",   "phone_e164": "+96170111004", "telegram_user_id": None},
    {"id": "aaaaaaaa-0000-0000-0000-000000000005", "display_name": "Nadia Frem",     "phone_e164": "+96170111005", "telegram_user_id": None},
]

MOCK_ORDERS = [
    {"id": "bbbbbbbb-0000-0000-0000-000000000001", "customer_id": "aaaaaaaa-0000-0000-0000-000000000001", "fulfillment": "delivery",  "hours_ago": 48},
    {"id": "bbbbbbbb-0000-0000-0000-000000000002", "customer_id": "aaaaaaaa-0000-0000-0000-000000000002", "fulfillment": "pickup",    "hours_ago": 36},
    {"id": "bbbbbbbb-0000-0000-0000-000000000003", "customer_id": "aaaaaaaa-0000-0000-0000-000000000003", "fulfillment": "delivery",  "hours_ago": 24},
    {"id": "bbbbbbbb-0000-0000-0000-000000000004", "customer_id": "aaaaaaaa-0000-0000-0000-000000000004", "fulfillment": "delivery",  "hours_ago": 12},
    {"id": "bbbbbbbb-0000-0000-0000-000000000005", "customer_id": "aaaaaaaa-0000-0000-0000-000000000005", "fulfillment": "pickup",    "hours_ago": 2},
]

MOCK_FEEDBACK = [
    {
        "order_id":   "bbbbbbbb-0000-0000-0000-000000000001",
        "customer_id":"aaaaaaaa-0000-0000-0000-000000000001",
        "star_rating": 5,
        "comment":    "Everything was perfect! The hummus was amazing and delivery was fast.",
        "sentiment":  "good",
        "status":     "received",
        "hours_ago":  46,
        "responded_hours_ago": 45,
    },
    {
        "order_id":   "bbbbbbbb-0000-0000-0000-000000000002",
        "customer_id":"aaaaaaaa-0000-0000-0000-000000000002",
        "star_rating": 2,
        "comment":    "Order was late and the fattoush was soggy. Disappointed.",
        "sentiment":  "bad",
        "status":     "received",
        "hours_ago":  34,
        "responded_hours_ago": 33,
    },
    {
        "order_id":   "bbbbbbbb-0000-0000-0000-000000000003",
        "customer_id":"aaaaaaaa-0000-0000-0000-000000000003",
        "star_rating": 3,
        "comment":    "Food was okay, nothing special.",
        "sentiment":  "neutral",
        "status":     "received",
        "hours_ago":  22,
        "responded_hours_ago": 21,
    },
    {
        "order_id":   "bbbbbbbb-0000-0000-0000-000000000004",
        "customer_id":"aaaaaaaa-0000-0000-0000-000000000004",
        "star_rating": None,
        "comment":    None,
        "sentiment":  None,
        "status":     "no_response",
        "hours_ago":  10,
        "responded_hours_ago": None,
    },
    {
        "order_id":   "bbbbbbbb-0000-0000-0000-000000000005",
        "customer_id":"aaaaaaaa-0000-0000-0000-000000000005",
        "star_rating": None,
        "comment":    None,
        "sentiment":  None,
        "status":     "pending",
        "hours_ago":  1,
        "responded_hours_ago": None,
    },
]


async def seed() -> None:
    db_url = _get_db_url()
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = datetime.now(tz=UTC)

    async with factory() as session:
        # Customers
        for c in MOCK_CUSTOMERS:
            await session.execute(text("""
                INSERT INTO customers (id, display_name, phone_e164, telegram_user_id, created_at, last_seen_at)
                VALUES (:id, :display_name, :phone_e164, :tg, now(), now())
                ON CONFLICT (id) DO NOTHING
            """), {"id": c["id"], "display_name": c["display_name"],
                   "phone_e164": c["phone_e164"], "tg": c["telegram_user_id"]})

        # Orders
        for o in MOCK_ORDERS:
            created = now - timedelta(hours=o["hours_ago"])
            await session.execute(text("""
                INSERT INTO orders (id, customer_id, items_snapshot, fulfillment, language,
                                    transcript_url, estimated_total_usd, flags, state, created_at)
                VALUES (:id, :customer_id, :items, :fulfillment, 'en',
                        '/api/transcripts/mock', 15.00, '[]', 'out_for_delivery', :created_at)
                ON CONFLICT (id) DO NOTHING
            """), {"id": o["id"], "customer_id": o["customer_id"],
                   "items": '[{"menu_item_id":"hummus","quantity":2,"customizations":[]}]',
                   "fulfillment": o["fulfillment"], "created_at": created})

        # Feedback
        for f in MOCK_FEEDBACK:
            requested = now - timedelta(hours=f["hours_ago"])
            responded = (now - timedelta(hours=f["responded_hours_ago"])) if f["responded_hours_ago"] else None
            await session.execute(text("""
                INSERT INTO order_feedback
                    (id, order_id, customer_id, star_rating, comment, sentiment,
                     status, feedback_requested_at, responded_at, created_at)
                VALUES
                    (gen_random_uuid(), :order_id, :customer_id, :star_rating, :comment, :sentiment,
                     :status, :requested_at, :responded_at, :requested_at)
                ON CONFLICT (order_id) DO NOTHING
            """), {
                "order_id":    f["order_id"],
                "customer_id": f["customer_id"],
                "star_rating": f["star_rating"],
                "comment":     f["comment"],
                "sentiment":   f["sentiment"],
                "status":      f["status"],
                "requested_at": requested,
                "responded_at": responded,
            })

        await session.commit()

    await engine.dispose()
    print("✅ Seeded 5 mock customers, 5 mock orders, 5 mock feedback records.")
    print("   Breakdown: 1 good, 1 bad, 1 neutral, 1 no_response, 1 pending")


if __name__ == "__main__":
    asyncio.run(seed())
