# RestoAI Backend

Telegram takeaway ordering bot with dispatcher review for a Lebanese restaurant.
Customers order in English, Lebanese Arabic, or Arabizi; a human dispatcher reviews
and pushes confirmed orders to the POS.

## Quick start (5 minutes)

### Prerequisites

- Docker and Docker Compose
- A Telegram bot token (`@BotFather`)
- A Groq API key

### 1. Clone and configure

```bash
git clone <repo-url>
cd restoai-backend
cp .env.example .env
# Edit .env — fill in TELEGRAM_BOT_TOKEN, GROQ_API_KEY, DISPATCHER_API_TOKEN
```

### 2. Bring up the stack

```bash
docker compose up --build
```

This starts Postgres 16 + pgvector, Redis 7, runs Alembic migrations, then
starts the API server and the RQ background worker.

### 3. Verify

```bash
curl http://localhost:8000/healthz   # → {"status":"ok"}
curl http://localhost:8000/readyz    # → {"status":"ready"} once all deps are up
```

### 4. Start the bot (polling mode)

In development the bot uses long-polling by default (no public URL needed).
Leave `TELEGRAM_WEBHOOK_URL` blank in `.env` to use polling.

### Deeper walkthrough

See [`specs/001-takeaway-orders/quickstart.md`](specs/001-takeaway-orders/quickstart.md)
for the full US1 happy-path walkthrough, multilingual smoke checks, and failure-path
scenarios.

## Architecture

See [`ARCH.md`](ARCH.md) for the layered architecture overview, request lifecycle,
and data flow diagrams.

## Operations

See [`RUNBOOK.md`](RUNBOOK.md) for start/stop procedures, polling↔webhook switch,
RQ queue inspection, secret rotation, and migration rollback.

## Architecture decisions

See [`DECISIONS.md`](DECISIONS.md) for the ten recorded architecture decisions
and their rationale.
