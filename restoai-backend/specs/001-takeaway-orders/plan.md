# Implementation Plan: Telegram Takeaway Ordering with Dispatcher Review

**Branch**: `001-takeaway-orders` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-takeaway-orders/spec.md`

## Summary

RestoAI's first feature is a Telegram bot that lets a Lebanese restaurant's
customers order takeaway (delivery or pickup) end-to-end in English, Lebanese
Arabic, or Arabizi, while a human dispatcher remains the only path that pushes
an order to the Omega POS. The technical approach is an async Python 3.11 /
FastAPI backend, PostgreSQL 16 + pgvector for relational and embedding storage,
Redis 7 for short-lived conversation state and an RQ work queue, a
python-telegram-bot integration (polling in dev, webhook in prod), Groq for
all LLM calls (cheap models for mechanical work, a stronger model for
synthesis), and a locally-hosted `intfloat/multilingual-e5-large`
(sentence-transformers, CPU) for menu RAG embeddings. The repository
follows the Clean Architecture layering mandated by the project constitution
(`app/api`, `app/services`, `app/repositories`, `app/domain`, `app/infra`,
plus `app/db` for ORM). The frontend dispatcher dashboard is deferred — this
plan freezes the dispatcher HTTP contract that a Stitch-generated React UI
will consume in a later phase.

## Technical Context

**Language/Version**: Python 3.11.

**Primary Dependencies**: FastAPI, Pydantic 2 + pydantic-settings,
SQLAlchemy 2.x (async) + asyncpg, Alembic, redis-py (async) + RQ,
python-telegram-bot (async), groq (official Python SDK, async),
sentence-transformers + torch (CPU-only build) for local
`intfloat/multilingual-e5-large` embeddings, python-json-logger, joblib
(to load the existing `intent_classifier.joblib`), rapidfuzz (delivery-area
matching).

**Storage**: PostgreSQL 16 with pgvector for both relational data (customers,
orders, transcripts) and embedding storage (menu chunks). Redis 7 for
conversation state with 2-hour TTL, RQ job queue, and optional response
caching with TTL.

**Testing**: pytest + pytest-asyncio. Unit tests per service/tool with mocked
Groq, the local embedding client, and Telegram clients. Pydantic schema tests for valid + invalid
inputs at every boundary. One end-to-end happy-path test with all externals
mocked. Golden sets for the intent classifier (already exists) and RAG
retrieval (10–15 questions; built during Phase 1 implementation). CI runs
ruff, mypy on critical modules, and pytest on every push.

**Target Platform**: Linux x86_64 containers under Docker Compose for local
dev and production. Single-host deployment is sufficient for v1 scale.

**Project Type**: Web service (no frontend in this iteration). Telegram bot
front and dispatcher REST API surface are exposed by the same FastAPI app.

**Performance Goals**: A typical customer turn (incoming Telegram update →
reply) under 3 seconds p95 when no LLM-synthesis call is needed (cached/
mechanical paths), under 6 seconds p95 when a synthesis LLM call is needed.
Restaurant-domain integrity (order accuracy) is privileged over latency per
Principle III; these are budgets, not headline SLOs.

**Constraints**: Async-only request path (no `time.sleep`, no `requests`).
Two-hour Redis TTL for conversation state per spec assumption. All secrets
loaded at startup via pydantic-settings; missing required keys cause hard
boot failure. PII (phone, name, address) MUST be redacted before any log
write or LLM prompt — a single redaction utility in `app/infra` is the only
sanctioned path.

**Scale/Scope**: Single restaurant brand, single FastAPI process + one RQ
worker process, expected order volume on the order of low-thousands/day in
steady state. Multi-tenant operation, RLS, and HA are explicitly out of
scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-evaluated after Phase 1 design.*

This section enumerates how the proposed design satisfies each principle and
each operational constraint from `.specify/memory/constitution.md` v1.0.0.

### Principle I — Clean Architecture & Code Quality

- ✅ The layered layout in `app/api`, `app/services`, `app/repositories`,
  `app/domain`, `app/infra`, plus an `app/db` package holding SQLAlchemy ORM
  models imported only by repositories, matches the principle exactly.
- ✅ Routers (Telegram webhook, dispatcher REST) call services only.
  Repositories execute SQL only and never raise HTTP errors. Services own
  transaction boundaries with `async with session.begin()`.
- ✅ Pydantic 2 models are mandated at every external boundary: HTTP
  request/response, Telegram update payload (a thin `TelegramUpdateIn`
  wrapper over the SDK type when domain logic needs it), LLM-extraction
  outputs, tool inputs, and the dispatcher payload. The `Order Draft` /
  `Confirmed Order` shapes are defined as Pydantic domain models, with
  SQLAlchemy ORM as the persistence-side mirror.
- ✅ Type hints required everywhere; mypy runs on critical modules in CI.
- ✅ Code is decomposed across modules — no single `main.py` beyond a thin
  `app/main.py` that wires the FastAPI app and lifespan handlers.

### Principle II — Testing Standards & ML Evaluation Discipline

- ✅ Each tool/service is unit-tested in isolation with mocked Groq, the
  local embedding client, and Telegram clients (interfaces defined as
  Protocols in `app/domain` and implementations in `app/infra`). The local
  embedder is fakeable in tests via a deterministic stub that returns a
  fixed 1024-dim vector per input string.
- ✅ Pydantic schemas tested with valid + invalid inputs (parametrized
  tests).
- ✅ End-to-end test of the US1 happy path with all externals mocked.
- ✅ Intent classifier golden set already exists from training; the
  classifier is reused as-is, with a threshold test in CI that asserts macro
  F1 ≥ 0.93 (committed buffer below the trained 0.96 to allow normal
  variance).
- ✅ RAG retrieval golden set (10–15 menu questions) is created during the
  Phase 1 implementation and its hit@k threshold is committed in CI.
- ✅ Data-leakage rules from Principle II don't apply to this feature
  because no new models are trained; the intent classifier was trained
  separately with the discipline already enforced, and that pipeline is not
  part of this plan.

### Principle III — Multilingual, Human-in-the-Loop UX

- ✅ Multilingual-first: a `LanguageService` detects the language of every
  incoming message and routes the reply through a localized prompt
  template / response catalogue from the first commit. English, Lebanese
  Arabic, and Arabizi-input-with-English-reply are all in the baseline
  contract surface.
- ✅ Order accuracy over latency: the synthesis-tier prompt always re-reads
  the parsed cart back, and the confirmation gate (FR-017/FR-023) is
  enforced as a domain invariant in `OrderService.confirm()`, not at the
  HTTP layer.
- ✅ HITL: `OrderService.confirm()` only flips the draft to
  `awaiting_dispatcher`; nothing in the system writes to "POS-entered"
  except the dispatcher endpoint, and that endpoint is the only mutation
  path with that effect — checked by an integration test.
- ✅ Graceful degradation: every external adapter in `app/infra` raises a
  typed `ExternalDependencyError`. The conversation service catches it and
  emits a localized degradation message + escalation offer per FR-034. No
  stack trace ever reaches the Telegram chat.

### Principle IV — Performance & Cost Discipline

- ✅ Cost-conscious LLM tiering: a single `GroqClient` exposes
  `complete_mechanical(...)` (cheap model) and `complete_synthesis(...)`
  (stronger model) as distinct methods. Service code calls the appropriate
  tier and reviewers verify the choice at PR time.
- ✅ Cost logging: every `GroqClient` call emits a structured record
  `{model, input_tokens, output_tokens, est_cost_usd, request_id}`. The
  local embedder emits a lighter record `{model, n_inputs, latency_ms,
  est_cost_usd: 0.0, request_id}` so cost-accounting is uniform across
  the synthesis and embedding paths even though the local model has no
  per-call dollar cost. The request-id correlation is enforced via a
  `ContextVar` set by the FastAPI middleware.
- ✅ Caching: `Settings` and model paths are loaded once and cached with
  `functools.lru_cache`. Tool responses (e.g., delivery-area lookup for the
  same input within 10 minutes) are cached with TTL in Redis.
- ✅ Async throughout: FastAPI routes async, asyncpg via SQLAlchemy async,
  `httpx.AsyncClient` for any direct HTTP, async Groq methods. The local
  embedder is sync (PyTorch CPU) and is therefore offloaded to a
  thread-pool via `asyncio.to_thread(...)` from any async caller, so the
  request path remains non-blocking. A `ruff` rule and a unit test forbid
  `time.sleep` and `requests` imports in `app/api` and `app/services`.

### Principle V — Security & Data Integrity

- ✅ Secrets resolved at startup via pydantic-settings; the `Settings` model
  marks `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `DATABASE_URL`, `REDIS_URL`,
  `DISPATCHER_API_TOKEN` as required. App refuses to boot on missing
  values; a unit test asserts this by constructing `Settings` with each
  required key removed. The embedding stack is local and therefore needs
  no API key.
- ✅ `.gitignore` excludes `.env`, `*.sqlite`, the venv folder, model
  artifacts that are not committed, and any pytest caches. `.env.example`
  is committed listing every key with placeholder values.
- ✅ PII redaction layer (`app/infra/redaction.py`) wraps phone numbers,
  names, and free-form addresses with deterministic tokens. The JSON
  logging formatter and every adapter that prepares LLM prompts go through
  it. A dedicated `tests/infra/test_redaction.py` proves the layer
  redacts Lebanese phone formats, common Arabic name patterns, and
  addresses (street/landmark style).
- ✅ ML/AI integrity (data leakage): not applicable to this plan — the only
  pre-trained artifact reused is the existing intent classifier, and no new
  training occurs here.

### Principle VI — Documentation as a First-Class Deliverable

- ✅ `DECISIONS.md` is created by the first PR of this plan and is appended
  to whenever a cross-module decision is made. The entries the plan
  promises are listed in the "Architecture decisions to record" section
  below.
- ✅ `ARCH.md` describes the layered architecture, request lifecycle,
  external integrations, and data flow — written as part of Phase 1.
- ✅ `RUNBOOK.md` documents `docker compose up --build`, how to switch
  Telegram between polling and webhook, how to inspect the RQ queue, how
  to rotate secrets, how to run a single golden-set evaluation, and how
  to roll back a migration.
- ✅ `README.md` is the five-minute setup guide.
- ✅ Every technology choice in this plan is justified by a number or a
  concrete tradeoff — the intent classifier carries a measured F1; the
  local `multilingual-e5-large` choice (vs. Cohere v3 or `bge-m3`) is
  justified in `research.md` R2 with a documented validation plan against
  the RAG golden set; LLM model selection is reviewed quarterly against
  the cost log.

### Operational Constraints (from constitution §Operational Constraints)

| Constraint | How satisfied |
|---|---|
| Layered layout | `app/api`, `app/services`, `app/repositories`, `app/domain`, `app/infra`, `app/db` — see Project Structure below. Cross-layer imports flow inward only; enforced by a `tests/architecture/test_layering.py` check. |
| Boundary types | Pydantic models for HTTP request/response, dispatcher payload, Telegram update DTO, LLM extraction outputs, tool inputs, RQ job payloads. |
| Async-only request path | Lint rule forbids `time.sleep` and `requests` in `app/api`/`app/services`; SQLAlchemy uses the async engine; LLM SDK calls use async methods. |
| Secrets at startup | `Settings` validates required keys; `app/main.py` calls `Settings()` before the lifespan handler attaches. Boot fails on missing keys. |
| PII redaction layer | Single `app/infra/redaction.py` utility; logging formatter and all LLM/embedding adapters import and apply it. Bypassing requires a documented exception in DECISIONS.md. |
| Cost logging | `app/infra/cost_log.py` writes a structured record on every Groq call and on every local-embedder call (the latter records `est_cost_usd: 0.0` for uniformity). Correlated by request id from a `ContextVar` set in FastAPI middleware. |
| Human confirmation | Order state machine forbids the `awaiting_dispatcher → entered_in_pos` transition without a dispatcher action; enforced in `OrderService.mark_entered_in_pos(dispatcher_id)` and asserted by an integration test. |

**Gate result**: ✅ All principles satisfied. No deviations recorded. Complexity Tracking table left empty by design.

## Project Structure

### Documentation (this feature)

```text
specs/001-takeaway-orders/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — dispatcher REST + Telegram webhook + internal tool contracts
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
restoai/
├── app/
│   ├── main.py                       # FastAPI app, lifespan: Settings, DB, Redis, classifier, Telegram bot
│   ├── api/
│   │   ├── deps.py                   # Depends() factories: DB session, services, request_id, current_dispatcher
│   │   ├── middleware.py             # request_id ContextVar, JSON access log
│   │   ├── telegram_router.py        # POST /telegram/webhook + polling task
│   │   ├── dispatcher/
│   │   │   ├── orders.py             # GET/PATCH /api/dispatcher/orders, POST /entered-in-pos
│   │   │   ├── escalations.py        # GET /api/dispatcher/escalations, POST /messages, POST /resolve
│   │   │   └── auth.py               # Bearer token / session check (single-tenant, lightweight)
│   │   └── health.py                 # /healthz, /readyz
│   ├── services/
│   │   ├── order_draft_service.py    # Build/edit drafts, attach customizations, in-zone check
│   │   ├── conversation_service.py   # Orchestrates intent → tool → LLM, handles language, failure counters
│   │   ├── dispatcher_service.py     # Queue listing, edits, mark-entered, escalation handoff
│   │   ├── language_service.py       # Detect → choose reply language per FR-028..FR-032
│   │   ├── menu_service.py           # Wraps menu repository + RAG; serves "show menu" and Q&A
│   │   ├── customer_service.py       # Recognition, profile collection
│   │   └── escalation_service.py     # 3-strike counter, queue-on-escalate, dispatcher↔customer bridge
│   ├── repositories/
│   │   ├── customer_repo.py
│   │   ├── order_repo.py             # ConfirmedOrder only — drafts are NOT here (Redis-only, see infra/draft_store)
│   │   ├── transcript_repo.py
│   │   ├── menu_repo.py              # Reads from data/menu_full_ar.json + pgvector chunks
│   │   └── zone_repo.py              # Reads from data/restaurant_info.json
│   ├── domain/
│   │   ├── customer.py               # Pydantic
│   │   ├── order.py                  # OrderDraft, ConfirmedOrder, OrderItem, Customization
│   │   ├── menu.py                   # MenuItem, MenuCategory
│   │   ├── conversation.py           # Conversation, Turn, FailureCounter
│   │   ├── language.py               # Language enum (EN, AR_LB, ARABIZI), DetectedLanguage
│   │   ├── tools.py                  # ToolInput/ToolOutput Pydantic models (one per tool)
│   │   └── errors.py                 # ExternalDependencyError, OrderValidationError, etc.
│   ├── infra/
│   │   ├── settings.py               # Pydantic Settings — required keys validated at startup
│   │   ├── logging.py                # JSON formatter, request_id ContextVar
│   │   ├── redaction.py              # PII redaction (phone, name, address) — single source of truth
│   │   ├── cost_log.py               # Per-call cost record
│   │   ├── groq_client.py            # complete_mechanical / complete_synthesis
│   │   ├── embed_client.py           # Local sentence-transformers (multilingual-e5-large), thread-pool offload
│   │   ├── telegram_client.py        # python-telegram-bot wrapper, polling+webhook modes
│   │   ├── redis_client.py           # Async Redis pool, RQ enqueue helper
│   │   ├── draft_store.py            # Redis-only OrderDraft: get/put/incr_failcount/delete with 2h TTL
│   │   └── intent_classifier.py      # joblib loader + classify(text) → Intent
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM (Customer, Address, Order, OrderItem, Transcript, MenuChunk, DispatcherAction)
│   │   ├── engine.py                 # Async engine, sessionmaker
│   │   └── alembic_env.py
│   ├── workers/
│   │   └── jobs.py                   # RQ jobs: draft_expiration_sweep, dispatcher_notify
│   └── prompts/
│       ├── en/                       # English prompt templates
│       ├── ar_lb/                    # Lebanese Arabic prompt templates
│       └── shared/                   # Language-agnostic system prompts
├── alembic/
│   ├── env.py
│   └── versions/
├── data/
│   ├── menu_full_ar.json             # Existing menu corpus (source of truth)
│   ├── restaurant_info.json          # Existing — delivery.areas is in-zone list
│   └── intent_classifier.joblib      # Existing — reused
├── tests/
│   ├── api/
│   ├── services/
│   ├── repositories/
│   ├── domain/
│   ├── infra/
│   │   └── test_redaction.py
│   ├── architecture/
│   │   └── test_layering.py          # asserts api → services → repositories → db boundary
│   ├── golden/
│   │   ├── intent/                   # existing test set + threshold
│   │   └── rag/                      # menu Q&A golden set
│   ├── e2e/
│   │   └── test_us1_happy_path.py
│   └── conftest.py
├── docker/
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── postgres.Dockerfile           # postgres:16 + pgvector
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml                    # ruff, mypy, pytest config
├── README.md
├── ARCH.md
├── DECISIONS.md
└── RUNBOOK.md
```

**Structure Decision**: Web service single-project layout (the constitutional
`app/{api,services,repositories,domain,infra}` six-pack plus `app/db` for
SQLAlchemy and `app/workers` for RQ jobs). Frontend is explicitly deferred;
the dispatcher REST contract under `app/api/dispatcher/` plus the OpenAPI
artifact in `contracts/` is the locked surface that a Stitch-generated React
UI will consume in a later phase. No `frontend/` directory exists yet.

## Architecture decisions to record

These will land in `DECISIONS.md` as part of the first PR of this plan and
will be expanded with the evidence collected during Phase 0 research:

1. **Single Postgres for relational + vector** vs. Qdrant/Chroma — chosen
   for operational simplicity and because the menu corpus is small (~100
   items, low thousands of chunks). Justification: one container fewer, one
   backup target, no cross-store consistency drift, pgvector is sufficient
   at this scale. Alternative considered: standalone vector store.
2. **Long polling in dev, webhook in prod** vs. ngrok always — chosen for
   zero-setup local iteration (no public URL) and explicit prod posture.
3. **Groq for all v1 LLM calls** vs. OpenAI/Anthropic — chosen for cost on
   bootcamp budget and Llama-3.1-class quality. Two-tier internal API
   (`complete_mechanical` vs. `complete_synthesis`) enforces Principle IV
   discipline regardless of provider.
4. **Local `intfloat/multilingual-e5-large` via sentence-transformers**
   vs. Cohere v3 or OpenAI embeddings — chosen for documented strong
   Arabic performance, zero API quota / trial-expiry risk, and adequate
   CPU latency at the corpus size; Cohere is the documented v2
   reconsideration if local inference becomes a bottleneck.
5. **python-telegram-bot** vs. aiogram vs. raw HTTP — chosen for community
   size, mature webhook+polling abstraction, and async support.
6. **Reuse trained `intent_classifier.joblib`** vs. LLM-classified intent —
   chosen because the existing model has measured macro F1 0.96 on its
   test set, runs in microseconds locally, and respects the
   cost-discipline principle (no LLM call needed for routing).
7. **Redis-only OrderDrafts (no Postgres snapshot)** — chosen to keep the
   draft write-path single-store, eliminate Redis/Postgres divergence
   bugs, and accept the explicit trade-off that a Redis restart loses
   at most 2 hours of in-flight drafts. Conversation transcripts are
   still written to Postgres on every turn so audit/escalation evidence
   is never lost; the first Postgres artifact in the order lifecycle is
   the `ConfirmedOrder`.
8. **Dispatcher attribution via self-reported `dispatcher_name` on every
   mutation** — chosen as the v1 audit-attribution surface alongside the
   shared bearer token. Bearer token gates access; the body field
   answers "who". Future per-user auth replaces the self-reported field
   without losing audit-history continuity.
9. **Existing `data/menu_full_ar.json` as menu source of truth** — chosen
   because it already exists and is curated; the menu repository loads it
   at startup and serves both menu rendering and the RAG chunk source.
10. **Frontend deferral** — backend exposes a complete dispatcher REST
    surface and OpenAPI schema; Google Stitch generates a React UI from
    that locked contract in a subsequent phase. API-first lets the
    contract stabilize before any UI code is written.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| *(none)*  |            |                                      |

No principles deviated from. No operational constraints relaxed.
