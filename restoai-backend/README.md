# RestoAI Backend

Telegram takeaway ordering bot with human dispatcher review for a Lebanese
restaurant. Customers order in English, Lebanese Arabic, or Arabizi; a human
dispatcher reviews confirmed orders and pushes them to the POS.

## Quick start (5 minutes)

### Prerequisites

- Docker and Docker Compose
- A Telegram bot token from `@BotFather`
- A Groq API key (free tier is sufficient)
- No embedding API key — `intfloat/multilingual-e5-large` runs locally

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

This builds the API and worker images, applies Alembic migrations to
Postgres 16 + pgvector, then starts the API server and the RQ background
worker. The first run downloads the ~1.3 GB embedding model into a named
Docker volume (`hfcache`) — subsequent rebuilds reuse the cache.

### 3. Verify

```bash
curl http://localhost:8000/healthz   # → {"status":"ok"}
curl http://localhost:8000/readyz    # → {"status":"ready"} once DB + Redis are up
```

### 4. Start chatting (development / polling mode)

In development the bot uses Telegram long-polling by default — no public
URL needed. Leave `TELEGRAM_WEBHOOK_URL` blank in `.env`, open your Telegram
client, and send `/start` to your bot.

### Deeper walkthrough

See [`specs/001-takeaway-orders/quickstart.md`](specs/001-takeaway-orders/quickstart.md)
for the full US1 happy-path walkthrough, multilingual smoke checks, and
failure-path scenarios.

---

## Technology

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL 16 + pgvector (asyncpg / SQLAlchemy 2 async) |
| Cache / queue | Redis 7 (redis-py async) + RQ |
| LLM | Groq API — Llama 3.1-8B (mechanical) / Llama 3.1-70B (synthesis) |
| Embeddings | `intfloat/multilingual-e5-large` via sentence-transformers (CPU) |
| Telegram | python-telegram-bot v21+ (polling in dev, webhook in prod) |
| Intent routing | scikit-learn classifier loaded from `data/intent_classifier.joblib` |
| Migrations | Alembic |
| Linting / types | ruff + mypy |
| Testing | pytest + pytest-asyncio |
| Containers | Docker Compose (single-host) |

---

## User stories

| Story | Description |
|-------|-------------|
| US1 | Customer places a takeaway order via Telegram; dispatcher reviews and marks as entered |
| US2 | Customer asks menu questions; bot answers via RAG over the menu corpus |
| US3 | Customer adds customizations (add/remove ingredients, cook preferences) |
| US4 | Returning customer greeted by name; saved addresses offered as one-tap buttons |
| US5 | After 3 consecutive failures the chat escalates to a human dispatcher |

---

## Development

### Running tests locally (without Docker)

```bash
# Install dependencies
pip install uv
uv sync

# Linting and type checking
uv tool run ruff check .
uv run mypy app/domain app/services app/api app/infra

# Unit and integration tests (no running DB or Redis required)
uv run pytest tests/architecture/ tests/infra/ tests/services/ tests/domain/ -v

# All tests (requires running Postgres + Redis — use docker compose for infra)
uv run pytest -v
```

### Running tests against the Docker stack

```bash
# Full suite inside the API container
docker compose run --rm api pytest -q

# End-to-end happy-path tests
docker compose run --rm api pytest tests/e2e/ -v

# Classifier + RAG golden-set thresholds
docker compose run --rm api pytest tests/golden/ -v
```

---

## Key reference documents

| Document | Contents |
|----------|---------|
| [`ARCH.md`](ARCH.md) | Layered architecture diagram, request lifecycles, data flows |
| [`RUNBOOK.md`](RUNBOOK.md) | Start/stop, polling↔webhook, RQ inspection, secret rotation, migration rollback |
| [`DECISIONS.md`](DECISIONS.md) | Ten architecture decision records with rationale and implementation evidence |
| [`specs/001-takeaway-orders/quickstart.md`](specs/001-takeaway-orders/quickstart.md) | End-to-end walkthrough and smoke checks |
| [`specs/001-takeaway-orders/plan.md`](specs/001-takeaway-orders/plan.md) | Full implementation plan with constitution compliance check |
