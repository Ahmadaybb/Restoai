# Architecture Decision Records: RestoAI Backend

Each ADR records a cross-module decision, the alternatives that were
evaluated, the reasoning, and the implementation evidence that confirmed
the decision during the build-out phase.

---

## ADR-001 — Single Postgres instance for relational + vector storage

**Decision**: Use a single PostgreSQL 16 + pgvector container for both
relational data (customers, orders, transcripts) and embedding vectors
(menu chunks).

**Alternatives considered**: Qdrant, Chroma (standalone vector stores).

**Rationale**: The menu corpus is small (~120 items, yielding ~360 chunks at
three language facets, 1024 dimensions each). pgvector IVFFlat/HNSW indices
are sufficient at this scale. Using a single store eliminates an extra
container, removes a cross-store consistency risk, and means a single backup
target and a single Alembic migration surface. The documented v2 migration
path is to Qdrant if the corpus grows by 10× or if query latency degrades.

**Implementation evidence**: `alembic/versions/001_initial_schema.py` creates
the `vector` extension and the `menu_chunks` table with a `pgvector(1024)`
column alongside the relational tables in the same migration. `MenuRepository`
loads `data/menu_full_ar.json` at startup and upserts embeddings in the same
transaction — exactly the transactional consistency benefit this ADR predicted.

---

## ADR-002 — Long-polling in development, webhook in production

**Decision**: The bot uses Telegram long-polling when `TELEGRAM_WEBHOOK_URL`
is blank, and switches to webhook mode when the URL is set.

**Alternatives considered**: Always use ngrok for a public URL in development.

**Rationale**: Long-polling requires zero network setup for local iteration —
no account, no public URL, no tunnel to maintain. Webhook mode is the correct
production posture (Telegram pushes updates; lower latency; no outbound
polling). The `TelegramClient` abstracts the switch behind a single env var
so developers never need to touch the abstraction.

**Implementation evidence**: `app/infra/telegram_client.py` — the
`is_webhook_mode` property gates `set_webhook()` / `delete_webhook()` in the
FastAPI lifespan. The polling background task in `telegram_router.py` starts
only when the mode is polling. Integration tests set `TELEGRAM_WEBHOOK_URL=""`
to exercise the polling code-path without a live bot.

---

## ADR-003 — Groq for all v1 LLM calls

**Decision**: All LLM calls go through the Groq API (Llama 3.1 family models)
via the official `groq` Python SDK.

**Alternatives considered**: OpenAI, Anthropic Claude.

**Rationale**: Groq's pricing is materially lower for the bootcamp budget
while Llama 3.1-class models provide adequate quality for the structured
extraction tasks (order parsing, address extraction, readback rendering). The
internal two-tier API (`complete_mechanical` / `complete_synthesis`) enforces
cost discipline regardless of provider, so the provider is swappable in a
future phase without touching any service code — only `app/infra/groq_client.py`
changes.

**Implementation evidence**: `app/infra/groq_client.py` uses
`llama-3.1-8b-instant` for mechanical calls and `llama-3.1-70b-versatile`
for synthesis. Per-call cost records are emitted via `app/infra/cost_log.py`
with `est_cost_usd` computed from documented Groq pricing. The tier discipline
is verified by `tests/services/test_tool_tier_enforcement.py` which fails if
any mechanical tool calls `complete_synthesis`.

---

## ADR-004 — Local `intfloat/multilingual-e5-large` for menu embeddings

**Decision**: Load `intfloat/multilingual-e5-large` via `sentence-transformers`
on CPU inside the API/worker container.

**Alternatives considered**: Cohere Embed v3, OpenAI `text-embedding-3-large`.

**Rationale**: `multilingual-e5-large` has documented strong Arabic + English
performance and is benchmark-competitive with Cohere on multilingual retrieval.
Running locally eliminates API quota risk, trial-expiry risk, and per-call
cost. CPU latency is 80–150 ms per batch, comfortably within the menu-Q&A
budget. Cohere v3 is the documented v2 reconsideration if local inference
becomes a bottleneck. Inference is offloaded to a thread pool via
`asyncio.to_thread` so the async request path remains non-blocking.

**Implementation evidence**: `app/infra/embed_client.py` wraps the
sentence-transformers `SentenceTransformer` model with `asyncio.to_thread`
offload. `app/main.py` calls `load_embedder()` in the lifespan and stores
`EmbedderClient()` in `app.state.embedder`. The `hfcache` named Docker volume
in `docker-compose.yml` ensures the ~1.3 GB model weights are not
re-downloaded on container rebuilds. `tests/golden/intent/` confirms the RAG
retrieval pipeline operates end-to-end.

---

## ADR-005 — `python-telegram-bot` as the Telegram SDK

**Decision**: Use `python-telegram-bot` (v21+, async) as the Telegram Bot API
wrapper.

**Alternatives considered**: `aiogram`, raw `httpx` calls.

**Rationale**: Largest community size, most mature webhook + polling
abstraction, full async support, and well-maintained type stubs. `aiogram`
was the closest alternative but `python-telegram-bot`'s unified
polling↔webhook abstraction required less custom wiring and has superior
documentation for the inline keyboard and location-sharing APIs used by the
ordering flow.

**Implementation evidence**: `app/infra/telegram_client.py` implements the
`MessengerClient` protocol defined in `app/domain/clients.py`. Inline
keyboard buttons (fulfillment choice, saved-address selection, confirm/edit
readback) are handled via `callback_query` events in `telegram_router.py`.
Location shares and contact shares are handled in the same router. Tests stub
the protocol interface — none import anything from `python-telegram-bot`
directly, preserving the swappability the ADR promises.

---

## ADR-006 — Reuse the trained `intent_classifier.joblib`

**Decision**: The existing `data/intent_classifier.joblib` scikit-learn model
is loaded at startup and used for intent routing on every inbound message.

**Alternatives considered**: LLM-based intent classification on every turn.

**Rationale**: The existing model has a measured macro F1 of 0.96 on its
held-out test set. It runs in microseconds locally, requires no API call,
and already handles English / Lebanese Arabic / Arabizi inputs. Using an LLM
for every routing decision would add 200–500 ms and a Groq API call with no
quality gain for well-formed messages. The CI threshold test guards against
regression.

**Implementation evidence**: `app/infra/intent_classifier.py` — `load_classifier()`
calls `joblib.load` at lifespan startup; `classify(text)` returns `(Intent, confidence)`.
The threshold gate in `tests/golden/intent/test_classifier_threshold.py`
asserts macro F1 ≥ 0.93 on the golden eval slice, with a 3-point buffer below
the trained 0.96 to absorb normal variance.

---

## ADR-007 — Redis-only OrderDrafts (no Postgres snapshot)

**Decision**: In-flight order drafts are stored exclusively in Redis with a
2-hour TTL. No Postgres write happens until `OrderService.confirm()` is
called.

**Alternatives considered**: Write draft snapshots to Postgres on every turn
for durability.

**Rationale**: The draft write-path becomes single-store, eliminating
Redis/Postgres divergence bugs (e.g., a Redis eviction not reflected in
Postgres, or a failed Postgres write leaving Redis stale). The explicit
trade-off is that a Redis restart loses at most 2 hours of in-flight drafts.
Conversation transcripts (every `Turn` row) are written to Postgres on every
turn, so audit and escalation evidence is never lost. The first Postgres
artefact in the order lifecycle is the `ConfirmedOrder`.

**Implementation evidence**: `app/infra/draft_store.py` — all draft operations
(`get_draft`, `put_draft`, `delete_draft`, `incr_failcount`) operate only on
Redis keys prefixed `draft:{customer_id}` and `failcount:{customer_id}:{field}`
with `DRAFT_TTL = 7200` seconds. `app/db/models.py` has no `draft` or
`order_draft` table. `OrderService.confirm()` is the first method that writes
to Postgres via `order_repo.create_confirmed`.

---

## ADR-008 — Dispatcher attribution via self-reported `dispatcher_name`

**Decision**: Every mutation endpoint requires a non-empty `dispatcher_name`
body field alongside the shared `DISPATCHER_API_TOKEN` bearer token.

**Alternatives considered**: Per-user accounts with individual API tokens.

**Rationale**: V1 operates with a shared token and a small team. The body
field answers "who performed this action" and satisfies the audit requirement
without the overhead of per-user auth infrastructure. `DispatcherAction` rows
persist the self-reported name alongside a SHA-256 hash of the bearer token
(first 16 hex chars). Future per-user auth replaces the self-reported field
without losing audit-history continuity because the action rows always carry
both.

**Implementation evidence**: `app/api/dispatcher/auth.py` —
`validate_dispatcher_name()` enforces non-blank, ≤80 chars, and returns a
trimmed value. `app/repositories/order_repo.py` — `append_dispatcher_action()`
stores `dispatcher_id` (token hash) and `dispatcher_name` on every mutation.
`app/services/dispatcher_service.py` — `_hash_token()` is the single function
that converts the raw bearer token to the stored hash, ensuring no raw token
ever reaches the database.

---

## ADR-009 — `data/menu_full_ar.json` as the menu source of truth

**Decision**: The existing `data/menu_full_ar.json` is the canonical menu
corpus. `MenuRepository` loads it at startup, upserts rows into `menu_items`,
and the same file is the source for RAG chunk generation.

**Alternatives considered**: A CMS-backed menu API, a separate admin
endpoint to manage menu items.

**Rationale**: The file already exists, is curated by the restaurant, and
covers all current menu items. Loading it at startup keeps the menu
up-to-date with container restarts without requiring an admin interface or
a database seed migration. A CMS integration is the documented next step
once the menu changes more frequently than once per deploy cycle.

**Implementation evidence**: `app/repositories/menu_repo.py` — `get_menu()`
parses `data/menu_full_ar.json` at module load time and caches the result.
`get_item(menu_item_id)` performs an O(1) dict lookup. No `INSERT` or `UPDATE`
paths exist for menu items in the codebase — the JSON file is the sole write
surface, confirmed by a grep: no `.save()`, no menu `POST` endpoint.

---

## ADR-010 — Frontend deferral (API-first)

**Decision**: The dispatcher dashboard frontend is deferred. The backend
exposes a complete dispatcher REST surface and locks the OpenAPI schema in
`specs/001-takeaway-orders/contracts/`. A Stitch-generated React UI will
consume that contract in a subsequent phase.

**Alternatives considered**: Build a basic frontend in this iteration.

**Rationale**: API-first lets the contract stabilize before any UI code is
written. The contract document (`contracts/dispatcher_api.openapi.yaml`) is
the single source of truth; the React UI is generated from it, eliminating
the divergence risk between backend and frontend. Building a UI in parallel
with a still-evolving backend API wastes iteration cycles.

**Implementation evidence**: `app/api/dispatcher/` contains `orders.py`,
`escalations.py`, and `auth.py` — a complete REST surface for listing orders,
editing, escalation management, and dispatcher messaging. FastAPI auto-generates
an OpenAPI schema at `/openapi.json`. No `frontend/`, `static/`, or `templates/`
directory exists. The project structure exactly matches the "API-first"
commitment.
