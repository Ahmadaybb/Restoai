# Architecture Decision Records: RestoAI Backend

## ADR-001 — Single Postgres instance for relational + vector storage

**Decision**: Use a single PostgreSQL 16 + pgvector container for both relational
data (customers, orders, transcripts) and embedding vectors (menu chunks).

**Alternatives considered**: Qdrant, Chroma (standalone vector stores).

**Rationale**: The menu corpus is small (~100 items, low-thousands of chunks at
1024 dimensions). pgvector IVFFlat/HNSW indices are sufficient at this scale.
Using a single store eliminates an extra container, removes a cross-store
consistency risk, and means a single backup target. The documented v2 migration
path is to Qdrant if the corpus grows or if query latency degrades.

---

## ADR-002 — Long-polling in development, webhook in production

**Decision**: The bot uses Telegram long-polling when `TELEGRAM_WEBHOOK_URL` is
blank, and switches to webhook mode when the URL is set.

**Alternatives considered**: Always use ngrok for a public URL in development.

**Rationale**: Long-polling requires zero network setup for local iteration.
Webhook mode is the correct production posture (lower latency, no outbound
polling). The `TelegramClient` abstracts the switch behind a single setting.

---

## ADR-003 — Groq for all v1 LLM calls

**Decision**: All LLM calls go through the Groq API (Llama 3.1 family models)
via the official `groq` Python SDK.

**Alternatives considered**: OpenAI, Anthropic Claude.

**Rationale**: Groq's pricing is significantly lower for the bootcamp budget
while Llama 3.1 class models provide adequate quality for the task. The
internal two-tier API (`complete_mechanical` / `complete_synthesis`) enforces
cost discipline regardless of provider, so the provider can be swapped in a
future phase without touching service code.

---

## ADR-004 — Local `intfloat/multilingual-e5-large` for menu embeddings

**Decision**: Load `intfloat/multilingual-e5-large` via `sentence-transformers`
on CPU inside the API/worker container.

**Alternatives considered**: Cohere Embed v3, OpenAI `text-embedding-3-large`.

**Rationale**: `multilingual-e5-large` has documented strong Arabic + English
performance. Running locally eliminates API quota risk, trial-expiry risk, and
per-call cost. CPU latency is acceptable at the menu corpus size (low-thousands
of vectors). Cohere v3 is the documented v2 reconsideration if local inference
becomes a bottleneck. Inference is offloaded to a thread pool via
`asyncio.to_thread` so the async request path remains non-blocking.

---

## ADR-005 — `python-telegram-bot` as the Telegram SDK

**Decision**: Use `python-telegram-bot` (v21+, async) as the Telegram Bot API
wrapper.

**Alternatives considered**: `aiogram`, raw `httpx` calls.

**Rationale**: Largest community, most mature webhook + polling abstraction,
full async support, and well-maintained type stubs. `aiogram` was a close
second but `python-telegram-bot`'s polling↔webhook abstraction required less
custom wiring.

---

## ADR-006 — Reuse the trained `intent_classifier.joblib`

**Decision**: The existing `data/intent_classifier.joblib` scikit-learn model
is loaded at startup and used for intent routing on every inbound message.

**Alternatives considered**: LLM-based intent classification on every turn.

**Rationale**: The existing model has a measured macro F1 of 0.96 on its
held-out test set. It runs in microseconds locally and requires no API call.
Using an LLM for every routing decision would add latency and cost with no
quality gain. The CI threshold test (macro F1 ≥ 0.93) guards against
degradation.

---

## ADR-007 — Redis-only OrderDrafts (no Postgres snapshot)

**Decision**: In-flight order drafts are stored exclusively in Redis with a
2-hour TTL. No Postgres write happens until `OrderService.confirm()` is called.

**Alternatives considered**: Write draft snapshots to Postgres on every turn.

**Rationale**: The draft write-path becomes single-store, eliminating
Redis/Postgres divergence bugs. The explicit trade-off is that a Redis restart
loses at most 2 hours of in-flight drafts. Conversation transcripts (every
`Turn` row) are still written to Postgres on every turn, so audit and
escalation evidence is never lost. The first Postgres artefact in the order
lifecycle is the `ConfirmedOrder`.

---

## ADR-008 — Dispatcher attribution via self-reported `dispatcher_name`

**Decision**: Every mutation endpoint requires a non-empty `dispatcher_name`
body field alongside the shared `DISPATCHER_API_TOKEN` bearer token.

**Alternatives considered**: Per-user accounts with individual API tokens.

**Rationale**: V1 operates with a shared token and a small team. The body
field answers "who performed this action" and satisfies the audit requirement
without the overhead of per-user auth infrastructure. `DispatcherAction` rows
persist the self-reported name alongside a hash of the bearer token. Future
per-user auth replaces the self-reported field without losing audit-history
continuity.

---

## ADR-009 — `data/menu_full_ar.json` as the menu source of truth

**Decision**: The existing `data/menu_full_ar.json` is the canonical menu
corpus. `MenuRepository` loads it at startup, upserts rows into `menu_items`,
and the same file is the source for RAG chunk generation.

**Alternatives considered**: A CMS-backed menu API, a separate admin endpoint.

**Rationale**: The file already exists, is curated by the restaurant, and
covers all current menu items. Loading it at startup keeps the menu
up-to-date with container restarts without requiring an admin interface.
A CMS integration is the documented next step once the menu changes more
frequently than once per deploy.

---

## ADR-010 — Frontend deferral (API-first)

**Decision**: The dispatcher dashboard frontend is deferred. The backend
exposes a complete dispatcher REST surface and locks the OpenAPI schema in
`specs/001-takeaway-orders/contracts/dispatcher_api.openapi.yaml`. A
Stitch-generated React UI will consume that contract in a subsequent phase.

**Alternatives considered**: Build the frontend in this iteration.

**Rationale**: API-first lets the contract stabilize before any UI code is
written. The contract document is the single source of truth; the React UI
is generated from it, eliminating divergence between backend and frontend.
