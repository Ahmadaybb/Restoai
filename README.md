# RestoAI

An AI-powered restaurant assistant that handles takeaway orders, reservations, and customer support via Telegram, with a dispatcher dashboard for staff.

---

## Overview

RestoAI consists of two services:

| Service | Stack | Purpose |
|---------|-------|---------|
| `restoai-backend` | Python 3.11, FastAPI, PostgreSQL, Redis | Telegram bot, order processing, LLM orchestration, dispatcher REST API |
| `restoai-frontend` | React 19, TypeScript, Vite, Tailwind CSS | Dispatcher dashboard — orders queue, escalations, reservations, settings |

The bot accepts orders in natural language (Arabic and English), parses them using a two-tier Groq LLM pipeline, confirms with the customer, and surfaces confirmed orders to the dispatcher dashboard. When the bot cannot handle a conversation, it escalates to a human dispatcher.

---

## Architecture

```
Customer (Telegram)
       │
       ▼
restoai-backend (FastAPI)
  ├── Telegram Bot (polling / webhook)
  ├── Intent Classifier (scikit-learn)
  ├── Order Draft Service (Redis)
  ├── LLM Tools — parse_order, match_dish, render_readback (Groq)
  ├── Menu RAG — vector search (pgvector + sentence-transformers)
  ├── PostgreSQL 16 — orders, customers, transcripts
  └── Dispatcher REST API
             │
             ▼
restoai-frontend (React)
  └── Dispatcher Dashboard
        ├── Orders Queue
        ├── Escalations / Live Chat
        ├── Reservations
        └── Settings
```

See [`restoai-backend/ARCH.md`](restoai-backend/ARCH.md) for detailed data flow diagrams.

---

## Prerequisites

- Docker and Docker Compose
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A [Groq](https://console.groq.com) API key
- Node.js 20+ (for running the frontend locally outside Docker)

---

## Quickstart

### 1. Clone the repo

```bash
git clone <repo-url>
cd restoai
```

### 2. Configure the backend

```bash
cp restoai-backend/.env.example restoai-backend/.env
```

Edit `restoai-backend/.env` and fill in the required values:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `GROQ_API_KEY` | Groq API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `DISPATCHER_API_TOKEN` | Bearer token for the dispatcher dashboard |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Leave `TELEGRAM_WEBHOOK_URL` blank for development (long-polling mode).

### 3. Configure the frontend

```bash
cp restoai-frontend/.env.example restoai-frontend/.env.local
```

Set `VITE_API_BASE_URL` to point at the backend (default: `http://localhost:8000`).

### 4. Start the backend

```bash
cd restoai-backend
docker compose up --build
```

This builds all images, runs database migrations, and starts `api`, `worker`, `db`, and `redis`.

Verify everything is healthy:

```bash
curl http://localhost:8000/healthz   # → {"status":"ok"}
curl http://localhost:8000/readyz    # → {"status":"ready"}
```

### 5. Start the frontend

```bash
cd restoai-frontend
npm install
npm run dev
```

The dashboard opens at `http://localhost:3000`.

---

## Development

### Backend

```bash
cd restoai-backend

# Lint + type-check
ruff check .
mypy app/domain app/services app/api app/infra

# Run tests
docker compose exec api pytest -q

# Run only end-to-end tests
docker compose exec api pytest tests/e2e/ -v
```

### Frontend

```bash
cd restoai-frontend

# Type-check
npm run lint

# Production build
npm run build
```

---

## Production Deployment

Switch the Telegram bot to webhook mode by setting these variables in `.env`:

```dotenv
TELEGRAM_WEBHOOK_URL=https://your-domain.example.com
TELEGRAM_WEBHOOK_SECRET=<random-string-min-32-chars>
TELEGRAM_WEBHOOK_SECRET_PATH=<random-url-segment>
```

Then restart the API container:

```bash
docker compose restart api
```

See [`restoai-backend/RUNBOOK.md`](restoai-backend/RUNBOOK.md) for secret rotation, log inspection, RQ queue management, and migration rollback procedures.

---

## Project Structure

```
restoai/
├── restoai-backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (Telegram, dispatcher, health)
│   │   ├── services/     # Business logic and LLM orchestration
│   │   ├── repositories/ # SQL + Redis persistence
│   │   ├── domain/       # Pydantic models and Protocols
│   │   ├── infra/        # External adapters (Groq, Telegram, Redis)
│   │   └── db/           # SQLAlchemy ORM models and engine
│   ├── alembic/          # Database migrations
│   ├── tests/            # Unit, integration, e2e, and golden-set tests
│   ├── data/             # Menu data and classifier artifacts
│   ├── docker-compose.yml
│   └── pyproject.toml
└── restoai-frontend/
    ├── src/
    │   ├── components/   # OrdersQueue, EscalationsList, ReservationsList, etc.
    │   ├── api/          # Backend API client
    │   └── App.tsx
    └── package.json
```

---

## License

Private — all rights reserved.
