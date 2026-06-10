# Quickstart — Telegram Takeaway Ordering

**Feature**: `001-takeaway-orders` | **Date**: 2026-06-10

This guide explains how to run RestoAI locally and validate the
US1 happy-path end-to-end. It is a *validation* guide — actual
implementation steps live in `tasks.md`, not here.

## Prerequisites

- Docker Desktop (Windows 11) with WSL2 backend or Docker Engine 24+.
- A Telegram bot token (BotFather `/newbot`).
- A Groq API key (free tier is fine for v1).
- No embedding API key — `intfloat/multilingual-e5-large` runs locally
  via sentence-transformers. The first `docker compose up --build` will
  download the ~1.3 GB model weights into a named volume
  (`hfcache`); subsequent rebuilds reuse the cache.

## One-time setup

1. Copy `.env.example` to `.env`. Fill in:

   ```dotenv
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_WEBHOOK_URL=               # leave empty for dev (polling mode)
   TELEGRAM_WEBHOOK_SECRET=
   TELEGRAM_WEBHOOK_SECRET_PATH=
   GROQ_API_KEY=...
   DATABASE_URL=postgresql+asyncpg://restoai:restoai@db:5432/restoai
   REDIS_URL=redis://redis:6379/0
   DISPATCHER_API_TOKEN=dev-dispatcher-token
   LOG_LEVEL=INFO
   ```

   Boot will hard-fail if any required key is missing
   (Principle V; pydantic-settings).

2. Confirm `data/menu_full_ar.json` and `data/restaurant_info.json` are
   present in the repo. They are the source of truth for the menu and
   the delivery-zone list respectively. `data/intent_classifier.joblib`
   must also be present.

## Bring up the stack

```powershell
docker compose up --build
```

Compose services and their roles:

| Service  | Purpose |
|----------|---------|
| `migrate`| Runs `alembic upgrade head` then exits. Creates the `vector` extension and the schema in `data-model.md`. |
| `db`     | Postgres 16 + pgvector. Named volume `pgdata`. |
| `redis`  | Redis 7. Named volume `redisdata`. |
| `api`    | FastAPI app, depends on `migrate` (zero exit) and `redis`. |
| `worker` | RQ worker for background jobs. |

`api` is ready when `GET http://localhost:8000/readyz` returns 200.

## Verify the contract surfaces

```powershell
# Dispatcher OpenAPI schema served from FastAPI
curl http://localhost:8000/openapi.json | jq '.paths | keys' | head

# Empty queue at boot
curl -H "Authorization: Bearer dev-dispatcher-token" `
  http://localhost:8000/api/dispatcher/orders
# → {"orders": []}
```

## US1 end-to-end validation (happy path)

1. Open your Telegram client and start a chat with your bot
   (`/start`).
2. Expect: a localized welcome message and the menu (categories with
   items) — FR-001, FR-002. The reply language follows your input
   language; `/start` defaults to English.
3. Send: `2 hummus, 1 fattoush, 1 grilled chicken`. Expect the bot to
   confirm the parsed items and ask for delivery vs pickup — FR-003,
   FR-009.
4. Tap `🛵 Delivery`. Expect a prompt to share your address; you may
   either type one or send a Telegram Location — FR-010.
5. Send: `Hamra Street near AUB`. Expect the bot to proceed (Hamra is
   in zone). Send `[some random out-of-zone area]` and you should see a
   localized warning per FR-035 — but the flow continues.
6. The bot reads back the full order (items, customizations, address,
   estimated total, plus the "final pricing is confirmed by the
   dispatcher" note) with inline `✅ Confirm` / `✏️ Edit` buttons —
   FR-016.
7. Tap `✅ Confirm`. Expect a "Thanks — sending to our team" message —
   FR-017.
8. In another terminal:

   ```powershell
   curl -H "Authorization: Bearer dev-dispatcher-token" `
     http://localhost:8000/api/dispatcher/orders | jq
   ```

   The order MUST appear with every field listed in FR-020.

9. POST to `/api/dispatcher/orders/{id}/entered-in-pos`. Expect the
   order state to flip to `entered_in_pos` and `entered_in_pos_at` to
   be set — FR-022.

If every step above passes, US1 is green. Each subsequent user story has
its own short scenario in `spec.md` under "Independent Test".

## Multilingual smoke check (Principle III)

- English input → English reply.
- Arabic (Lebanese dialect) input (e.g., `بدي 2 حمص و 1 فتوش`) → Arabic
  reply.
- Arabizi input (e.g., `bade 2 hummus w 1 fattoush`) → English reply
  the customer can read.

Routing accuracy on the held-out language-detection set must be ≥ 95% in
CI (SC-005).

## Failure-path smoke checks (FR-034)

- Stop the `redis` container while a chat is mid-flow. The bot must
  reply with a localized "we're having a hiccup, please try again in a
  moment" message — never a stack trace.
- Stop the `groq` route by setting `GROQ_API_KEY` to an invalid value
  and restarting `api`. Expect FR-034 graceful degradation messaging
  and an "escalate to a human" option.

## Test-suite validation

```powershell
docker compose run --rm api pytest -q
docker compose run --rm api pytest -q tests/golden  # classifier + RAG thresholds
docker compose run --rm api pytest -q tests/e2e     # US1 happy-path
```

CI runs the same suites on every push (GitHub Actions).

## Tear down

```powershell
docker compose down            # keep named volumes
docker compose down -v         # also drop pgdata + redisdata (fresh slate)
```

## Where to go from here

- `tasks.md` will be generated by `/speckit-tasks` and contains the
  implementation steps in dependency order, grouped by user story.
- `ARCH.md`, `DECISIONS.md`, `RUNBOOK.md` (Principle VI) are written
  alongside the implementation; the first PR creates the skeletons.
