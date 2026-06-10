# Phase 0 Research: Telegram Takeaway Ordering

**Feature**: `001-takeaway-orders` | **Date**: 2026-06-10

This document resolves the open technical questions implied by
`plan.md`'s Technical Context. Each item follows the format **Decision /
Rationale / Alternatives considered**. Items that are direct user-input
choices (Python 3.11, FastAPI, Docker Compose) are not re-litigated here —
they are stated as `Given:` for traceability.

---

## R1 — Vector store: pgvector vs. dedicated vector DB

**Decision**: Use the `pgvector` extension inside the same PostgreSQL 16
instance that holds relational data. Single database, single backup target.

**Rationale**:
- Menu corpus is small (~120 items based on `data/menu_full_ar.json`).
  After chunking (one chunk per item × 3 language facets), the index size
  is on the order of ~400 vectors at 1024 dims (the embedding model
  selected in R2 returns 1024-dim). pgvector handles this trivially with
  `ivfflat` and even brute-force; no need for HNSW performance.
- One container fewer in `docker-compose.yml`; one backup pipeline;
  transactional consistency between relational data and embedding rows
  (we can re-embed within the same migration).
- Stacks well with the rest of the SQLAlchemy layer — embeddings are just
  a column on the `menu_chunk` table.

**Alternatives considered**:
- **Qdrant** — strong, but adds a service and a network hop for a corpus
  small enough to live inline. Re-introduce if/when the corpus grows by
  10×.
- **Chroma (local persistent)** — fine for prototypes; not great for
  Docker Compose orchestration and migrations alongside the relational
  store.
- **Faiss-in-memory** — rejected because the index needs to survive worker
  restarts and rebuilding from JSON at every boot is wasteful.

---

## R2 — Embedding model: local `intfloat/multilingual-e5-large`

**Decision**: Use `intfloat/multilingual-e5-large` running locally via
`sentence-transformers` inside the FastAPI process. The model is loaded
once at lifespan startup and exposed through `Depends()`. Embeddings are
1024-dim and stored in `pgvector`. Inference runs on CPU — no GPU
container required given the small menu corpus (~120 items × ~3
language facets ≈ ~360 vectors). Per-query latency on CPU is roughly
80–150 ms, comfortably within the FR-007 response budget. There is no
API quota to manage, no trial expiry risk, and no third-party API key
required.

**Rationale**:
- **Bootcamp risk**: the Cohere free trial was 1000 calls/month and
  would have expired mid-development with no clean swap path. A local
  model removes the cliff.
- `multilingual-e5-large` is benchmark-competitive with Cohere
  `embed-multilingual-v3` on multilingual retrieval and has documented
  strong Arabic performance, which is the quality bar that matters for
  this feature.
- **Image-size cost**: ~1.3 GB for the model weights. Mitigated by
  mounting the Hugging Face cache from a named Docker volume
  (`hfcache:/root/.cache/huggingface`) so the model is not re-downloaded
  on container rebuilds.
- **Trade-off accepted**: ~80–150 ms CPU inference vs. ~30 ms Cohere
  API. This is acceptable for menu Q&A; the synthesis-tier LLM call
  dominates the turn budget anyway.
- One fewer external dependency on the request path — Principle IV
  (graceful degradation) gets simpler because embedding lookup cannot
  fail due to network/quota.

**Alternatives considered**:
- **Cohere `embed-multilingual-v3`** — rejected for v1 due to
  trial-expiry risk. Reconsider in v2 if local CPU inference becomes a
  bottleneck (e.g., corpus growth or higher concurrency).
- **OpenAI `text-embedding-3-large`** — comparable English quality,
  weaker on dialectal Arabic; mixed reports on transliterated input
  (Arabizi). Cost-per-call adds up at higher volume.
- **`BAAI/bge-m3` local** — also a strong candidate; chose e5 for its
  more established benchmark history on Arabic retrieval. bge-m3 is the
  documented fallback if e5 underperforms on the RAG golden set.

**Validation plan**: A small RAG golden set (10–15 questions in
EN / AR / Arabizi) is built during Phase 1 implementation. e5 is the
default; if hit@3 < 0.8 on the golden set, fall back to `bge-m3` local —
that exit is captured as a future DECISIONS.md entry, not pre-committed
here.

---

## R3 — LLM provider and tiering: Groq

**Decision**: Use Groq for all v1 LLM calls. Expose two methods on the
internal client:
- `GroqClient.complete_mechanical(...)` — Llama-3.1-8B-Instruct class
  (fast, cheap). Used for: language detection sanity check, intent
  classification fallback, query rewriting for RAG, structured-output
  extraction (order parse, address parse, customization mapping).
- `GroqClient.complete_synthesis(...)` — Llama-3.1-70B-Instruct class.
  Used for: read-back generation, RAG answer synthesis, escalation
  summary for dispatcher.

**Rationale**:
- Bootcamp-friendly pricing and free tier.
- Sub-second token throughput on Groq's hardware reduces tail latency for
  synthesis-heavy turns, supporting the Principle IV async-throughout
  posture.
- Llama-3.1-70B handles Arabic/Lebanese dialect reasonably well; spot-
  checked during the spec authoring phase.
- A single provider keeps the SDK surface, error model, and cost-logging
  shape uniform.

**Alternatives considered**:
- **OpenAI gpt-4o-mini + gpt-4o** — strong, but more expensive and
  unnecessary uplift on quality at v1 scale.
- **Anthropic Haiku 4.5 + Sonnet 4.6** — excellent, but Anthropic pricing
  is heavier than Groq for the synthesis tier; revisit when production
  volume justifies it.

**Cost-logging schema** (enforced by the constitution): every call writes
`{ts, request_id, provider="groq", model, tier, input_tokens,
output_tokens, est_cost_usd, latency_ms}`.

---

## R4 — Telegram integration library and operation mode

**Decision**: `python-telegram-bot` v21+ (async API). Long polling in dev,
webhook in prod, selected by the presence of `TELEGRAM_WEBHOOK_URL` in
env.

**Rationale**:
- Largest community and the only major Python Telegram lib with both a
  mature async surface AND solid webhook + polling abstractions.
- Polling in dev removes the need for ngrok or any public URL.
- Webhook in prod is mandatory for low-latency delivery and predictable
  scaling.
- `inline keyboard` and `callback_query` support is first-class — both
  required for the Confirm/Edit buttons (FR-016).

**Alternatives considered**:
- **aiogram 3.x** — also good, smaller community, more breaking changes
  historically.
- **Raw HTTP via httpx** — full control but we'd be reimplementing
  inline-keyboard callbacks and rate-limit retries.

**Operational note**: In webhook mode, the webhook endpoint
`POST /telegram/webhook` lives behind a secret path segment plus a
constant-time comparison against `TELEGRAM_WEBHOOK_SECRET`. In polling
mode, the FastAPI app starts a single background task at lifespan-startup
that runs the long-poll loop.

---

## R5 — Reuse of `intent_classifier.joblib` vs. LLM-based intent

**Decision**: Reuse the existing classifier (TF-IDF + LinearSVC, 5
intents: `order` / `reservation` / `query` / `status` / `image`, macro F1
0.96 on the held-out set). Loaded once at startup.

**Rationale**:
- Already trained; zero marginal cost. Principle IV: don't burn an LLM
  call where a 1ms classifier suffices.
- Macro F1 0.96 exceeds what we'd realistically get from a zero-shot LLM
  classifier at any tier, and is deterministic.
- A threshold test in CI (`tests/golden/intent`) asserts macro F1 ≥ 0.93
  on a frozen evaluation slice. Below threshold ⇒ CI fails.

**Fallback**: If the classifier's max-probability confidence is below a
calibrated threshold, the conversation service falls back to a single
Groq mechanical-tier call to disambiguate. This protects against
distribution shift while keeping cost predictable.

**Reservation/status/image intents** are explicitly out of scope for this
feature; the conversation service routes them to a "Coming soon" response
in the customer's language for v1.

---

## R6 — Conversation state store: Redis-only for active drafts

**Decision**: Active order drafts and per-conversation failure counters
live **only** in Redis with a 2-hour TTL. There is no Postgres snapshot
of in-flight drafts. If Redis is restarted, in-flight drafts are lost
and the customer's next message starts a fresh conversation — the bot's
welcome flow (FR-001) handles this gracefully.

Postgres holds: confirmed orders, conversation transcripts (written on
each turn), dispatcher actions, customer profiles, saved addresses, and
the in-zone area list. Postgres is the system of record for everything
the dispatcher reviews and for returning-customer recognition (FR-012).
Drafts are intentionally ephemeral state, not persisted history.

**Rationale**:
- **Simpler write path**: every draft update is one Redis call, not two.
  Services don't have to reason about which store is authoritative.
- **Removes a class of bugs**: a Postgres draft snapshot can diverge
  from the Redis live state under concurrent updates or partial
  failures. Eliminating the snapshot eliminates the divergence.
- **Honest trade**: a Redis restart costs at most two hours of
  in-progress drafts. The customer redoes the order. No confirmed-order
  history is lost, no audit log is lost, no data integrity issue.
- **Conversation transcripts are still written to Postgres on every
  turn** — so even mid-conversation state has an authoritative
  audit-quality record for escalations and dispute resolution. What is
  lost on a Redis restart is the *parsed cart shape*, not the
  conversation history.
- RQ continues to use this Redis instance for the worker queue (single
  Redis service in compose).

**Schema sketch** (full schema in `data-model.md`):
- `draft:{customer_id}` — Redis JSON blob, TTL 7200.
- `failcount:{customer_id}:{field}` — Redis int, TTL 7200.
- `chat_state:{customer_id}` — Redis JSON: current expectation
  (e.g., `awaiting_address`, `awaiting_confirmation`), `awaiting_human`
  flag, dispatcher id if escalated.

**Persistence boundary**: `ConfirmedOrder` is the first
Postgres-persisted artifact in the order lifecycle. Everything earlier
(items being built, fulfillment chosen, address gathered) is Redis-only.

---

## R7 — Address handling: free-form + Telegram Location

**Decision**: Store delivery addresses as a discriminated union:
`{kind: "text", value: str}` or `{kind: "location", lat: float, lon:
float, note: str | None}`. The bot accepts whichever the customer
provides; both can coexist (text + a "near" landmark plus optional
location pin).

**Rationale**:
- Lebanese addressing is landmark-based; forcing structured fields
  produces brittle UX and is rejected by the spec assumption.
- Telegram Location is a first-class chat message type; ignoring it
  forces customers to type something they've already shared via map pin.
- The in-zone check (FR-035) reads from the text portion: we run a fuzzy
  match (token-set ratio via `rapidfuzz`, threshold tunable) against the
  configured `delivery.areas` list from `data/restaurant_info.json`.

**Alternatives considered**:
- **Force structured input** — rejected per spec (landmark addressing is
  cultural).
- **Geocode every address with a third-party API** — rejected for v1 due
  to cost and latency; the dispatcher does the final delivery-zone
  judgment.

---

## R8 — In-zone area list source: `data/restaurant_info.json`

**Decision**: Load `restaurant_info.json` at startup and expose
`delivery.areas` (a list of Lebanese-Arabic + transliterated neighborhood
names) through `ZoneRepository`. Matching is fuzzy (rapidfuzz ≥ 80
threshold, configurable) and falls back to "not confident" when ambiguous
— in which case the bot proceeds *without* the warning, deferring the
judgment to the dispatcher.

**Rationale**:
- The areas list already exists in the file the user has opened. No
  duplication.
- A fuzzy match handles common spelling variants (Hamra/حمرا,
  Achrafieh/Ashrafieh/الأشرفية) without needing a separate normalization
  pipeline.
- "Not confident → don't warn" is the right default: the worst outcome is
  bothering the dispatcher needlessly, but the spec already accepts a
  dispatcher-final review on every order.

**Note**: The list in the current file contains a literal `[ADD MORE
AREAS - to be filled]` placeholder. The startup loader strips placeholder
entries (`^\[.*\]$` pattern) and emits a single WARN-level log line if
any were skipped — a recorded reminder, not a failure.

---

## R9 — Database migration strategy

**Decision**: Alembic, with a dedicated `migrate` service in
`docker-compose.yml` that runs `alembic upgrade head` and exits before
`api` and `worker` start. Healthcheck on `api`/`worker` depends on
`migrate` having exited zero.

**Rationale**:
- Idempotent and replayable.
- Separating migration from API boot prevents the "two replicas race the
  migration" footgun even though v1 is single-replica.
- The pgvector extension is created in the first migration
  (`CREATE EXTENSION IF NOT EXISTS vector`).

---

## R10 — RQ vs. Celery vs. arq

**Decision**: RQ (Redis Queue) for background jobs.

**Rationale**:
- Already using Redis; zero new infrastructure.
- Simple, well-understood; works well with the small set of jobs we
  need: `draft_expiration_sweep`, `dispatcher_notify`,
  `transcript_persist`.
- Async-friendly via `rq.job` workers that can call into our async code
  through `asyncio.run` shims at the job entry point. The hot request
  path remains fully async; only background workers cross the sync/async
  boundary.

**Alternatives considered**:
- **Celery** — overpowered for v1; adds broker complexity if we ever
  switch off Redis.
- **arq** — native async, smaller community. Reasonable choice; defer
  unless RQ's async-bridging shape becomes painful.

---

## R11 — JSON logging shape and request-id propagation

**Decision**: `python-json-logger`'s `JsonFormatter` with a custom
`Formatter` subclass that:
- Injects `request_id` from a `ContextVar` set by FastAPI middleware.
- Routes every record through `redaction.redact(...)` before emission.

**Rationale**:
- Stdout JSON is the lingua franca of every log shipper.
- A `ContextVar` propagates the id through `await` points without
  requiring every callee to pass it explicitly.
- Centralized redaction means the constitutional rule "PII MUST be
  redacted before any log line leaves the service" is enforced in one
  place that all code paths go through.

**Schema**: `{ts, level, logger, msg, request_id, customer_id?, model?,
input_tokens?, output_tokens?, est_cost_usd?, latency_ms?, redacted: bool}`.

---

## R12 — Dispatcher authentication and audit attribution for v1

**Decision**: Dispatcher authentication uses a single bearer token
(`DISPATCHER_API_TOKEN` env var) for v1. The token gates access to the
entire dispatcher REST surface. Multi-user auth, RBAC, and per-user
identity are deferred to a future spec.

In addition, **every state-changing dispatcher action** (mark entered in
POS, edit order, cancel order, take over escalation, send message to
customer, close handoff) MUST include a `dispatcher_name` field in the
request body. The audit log records `dispatcher_name` with each action
alongside the token-hash. This gives meaningful attribution in the
audit log without building a full user system in v1.

Read-only endpoints (list orders, view order, view escalations) do NOT
require `dispatcher_name` — only writes/mutations do.

**Validation**: `dispatcher_name` is a non-empty trimmed string, maximum
length 80 characters. Missing or empty values on a mutation endpoint
return HTTP 400 with a structured error message
(`{"code": "DISPATCHER_NAME_REQUIRED", "message": "..."}`).

**Rationale**:
- Single restaurant, small operations team, internal dashboard. A
  rotated team token is sufficient for access control.
- Self-reported `dispatcher_name` is a deliberate trust-on-honour
  compromise. It is not authentication; it is attribution for the audit
  log. A future per-user system will replace the self-reported field
  with an authenticated identity, and the column already exists.
- Token hash + self-reported name together are sufficient to answer
  "who marked this order entered in POS at 18:42 last Tuesday" in a
  follow-up dispute, which is the realistic v1 audit use case.

**Alternatives considered**:
- **Per-user accounts now** — overkill for solo bootcamp project;
  revisit when a real multi-dispatcher org appears.
- **Header-based attribution** (e.g., `X-Dispatcher-Name`) — moves the
  field out of the request body, but loses request/response validation
  via Pydantic and the OpenAPI contract. Rejected.
- **No attribution at all** — would leave the audit log unable to
  distinguish operators. Rejected; the audit log is a Principle V data-
  integrity surface.

---

## R13 — Frontend deferral: dispatcher API contract as the locked surface

**Decision**: No frontend in this iteration. The dispatcher REST API
surface is fully specified in `contracts/dispatcher_api.openapi.yaml`
(Phase 1 output) and is the artifact a Stitch-generated React UI will
later consume.

**Rationale**:
- Lets the contract stabilize before any UI code is written; the UI
  becomes a pure renderer of a fixed shape.
- The constitution allows it — there is nothing in Principles I–VI that
  requires a UI to ship before the contract.
- Reduces the surface area of this PR set; ships the bot end-to-end with
  a CLI/Postman-driven dispatcher exercise.

---

## R14 — Testing externals: mocking Groq, the local embedder, Telegram

**Decision**: Define `Protocol` classes in `app/domain` for each external
(`LLMClient`, `EmbeddingClient`, `MessengerClient`). Implementations in
`app/infra` satisfy the protocols. Tests inject hand-written fakes that
record calls and return canned responses. The local embedder is also
behind the `EmbeddingClient` protocol, so even though it has no network
dependency, the tests fake it the same way the LLM client is faked —
that keeps unit tests fast and deterministic.

**Rationale**:
- Type-checked seams. No `unittest.mock.patch` archeology.
- The protocol is also the document that says "here is the exact surface
  RestoAI's services expect" — useful when swapping Groq for another
  provider later.

---

## R15 — Out-of-scope confirmations

The following are explicitly **not** researched in this document because
the user input excluded them from scope:

- Frontend stack (React, Vite, Tailwind, shadcn/ui)
- HashiCorp Vault — env vars are sufficient for v1 per user input
- MinIO / blob storage
- Multi-tenancy / RLS
- Payments
- Reservations, image recognition, delivery status messages, feedback
  collection (separate specs)

These are recorded here so a future reader knows the choice to skip was
deliberate, not an oversight.

---

## Summary

All resolvable items in the Technical Context are decided. There are
zero residual `NEEDS CLARIFICATION` markers. The plan is ready to enter
Phase 1 design.

Notable v1 posture (post-amendment):

- **Embeddings**: local `intfloat/multilingual-e5-large` via
  sentence-transformers, CPU inference, ~1.3 GB model weights cached in
  a named Docker volume. No third-party embedding API key required.
- **Drafts**: Redis-only, 2-hour TTL, no Postgres snapshot. Postgres
  becomes authoritative only at `ConfirmedOrder`. Transcripts are still
  written to Postgres on every turn.
- **Dispatcher auth + audit**: single bearer token gates access;
  mutation endpoints additionally require `dispatcher_name` in the
  request body for audit attribution.
