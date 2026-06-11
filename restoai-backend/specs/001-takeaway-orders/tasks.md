---
description: "Dependency-ordered task list for feature 001-takeaway-orders"
---

# Tasks: Telegram Takeaway Ordering with Dispatcher Review

**Input**: Design documents from `/specs/001-takeaway-orders/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Tests are mandatory in this feature because the project constitution (Principle II) requires automated tests on critical paths, ML golden sets, and Pydantic schema validation. Test tasks are included throughout.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Story 0 is the shared foundation; US1–US5 are stacked in priority order per `spec.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: Maps a task to its user story (US1, US2, US3, US4, US5). Setup, Foundational, and Polish tasks have no story label.
- Every task description includes a concrete file path and references the spec FR(s) and/or contract section it implements.

---

## Phase 1: Setup (project initialization)

**Purpose**: Bring up the skeletal repository, the Docker Compose stack, and the documentation surface that the constitution (Principle VI) requires.

- [X] T001 Create the `app/` Clean Architecture skeleton (`app/api/`, `app/services/`, `app/repositories/`, `app/domain/`, `app/infra/`, `app/db/`, `app/workers/`, `app/prompts/{en,ar_lb,shared}/`) with empty `__init__.py` files. Layout per plan.md §Project Structure.
- [X] T002 [P] Create `pyproject.toml` declaring Python 3.11 and pinning: fastapi, pydantic 2, pydantic-settings, sqlalchemy[asyncio] 2.x, asyncpg, alembic, redis, rq, python-telegram-bot, groq, sentence-transformers, torch (CPU-only index), python-json-logger, joblib, rapidfuzz, pytest, pytest-asyncio, ruff, mypy. Source list: plan.md §Technical Context.
- [X] T003 [P] Create `.gitignore` excluding `.env`, `*.sqlite`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, and any committed-by-mistake model weights. Principle V §Security & Data Integrity.
- [X] T004 [P] Create `.env.example` listing every required key with placeholder values: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_SECRET_PATH`, `GROQ_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `DISPATCHER_API_TOKEN`, `LOG_LEVEL`. Per quickstart.md §One-time setup and research.md R12.
- [X] T005 [P] Configure ruff in `pyproject.toml` with rules that forbid `time.sleep` and `requests` imports in `app/api/**` and `app/services/**` (custom `[tool.ruff.lint.per-file-ignores]` + `flake8-bandit`/`tidy-imports` style check). Constitution §Operational Constraints — Async-only request path.
- [X] T006 [P] Configure mypy in `pyproject.toml` to type-check `app/domain/`, `app/services/`, `app/api/`, `app/infra/` strictly; allow `app/db/models.py` looser typing for SQLAlchemy. Constitution Principle I.
- [X] T007 [P] Configure pytest in `pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, register custom markers (`e2e`, `golden`).
- [X] T008 [P] Create `docker/api.Dockerfile` (python:3.11-slim base, install from pyproject, run `uvicorn app.main:app`).
- [X] T009 [P] Create `docker/worker.Dockerfile` (same base, runs the RQ worker entry point against `app/workers/jobs.py`).
- [X] T010 [P] Create `docker/postgres.Dockerfile` based on `pgvector/pgvector:pg16` with no other modifications. Source: research.md R1.
- [X] T011 Create `docker-compose.yml` declaring services `db`, `redis`, `migrate`, `api`, `worker` with the dependency chain `migrate exits 0 → api/worker start`, plus named volumes `pgdata`, `redisdata`, and `hfcache` (the Hugging Face cache for sentence-transformers weights). Per research.md R2 and R9 and quickstart.md §Bring up the stack.
- [X] T012 Verify `data/menu_full_ar.json`, `data/restaurant_info.json`, and `data/intent_classifier.joblib` exist at the repo root under `data/`; move them in from their source location if not yet present. Per plan.md §Project Structure and quickstart.md §One-time setup.
- [X] T013 [P] Create `README.md` as the 5-minute setup guide (constitution Principle VI; defers operator detail to `quickstart.md`).
- [X] T014 [P] Create `ARCH.md` skeleton with sections: Layered architecture overview, Request lifecycle, External integrations, Data flow. Principle VI.
- [X] T015 [P] Create `RUNBOOK.md` skeleton with sections: Start/stop, Polling↔webhook switch, RQ queue inspection, Secret rotation, Single-eval invocation, Migration rollback. Principle VI.
- [X] T016 [P] Create `DECISIONS.md` and seed the ten architecture decisions enumerated in plan.md §Architecture decisions to record (single Postgres+pgvector; polling/webhook split; Groq for v1; local multilingual-e5-large; python-telegram-bot; reuse intent_classifier.joblib; Redis-only drafts; dispatcher_name attribution; menu_full_ar.json as menu source; frontend deferral). Principle VI.
- [X] T017 [P] Create `.github/workflows/ci.yml` running ruff, mypy on critical modules, and pytest on every push. Constitution Principle II §Testing Standards.

---

## Phase 2: Foundational (blocking prerequisites) — Story 0

**Purpose**: Settings, logging, redaction, DB engine, Redis, ORM, FastAPI skeleton, domain models, external adapters. Nothing in US1–US5 can begin until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T018 Implement `app/infra/settings.py` with a Pydantic Settings class declaring `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `DISPATCHER_API_TOKEN` as required; optional polling/webhook fields and `LOG_LEVEL`. App MUST refuse to boot when a required key is missing. Constitution Principle V; research.md R12.
- [X] T019 Unit test in `tests/infra/test_settings_boot.py` proving `Settings()` raises a validation error when each required key is removed from the environment. Principle V §Operational Constraints.
- [X] T020 [P] Implement the PII redaction layer in `app/infra/redaction.py` covering Lebanese phone formats (`+961…`, `03 XXX XXX`, `70/71/76/78/79/81/03 …`), customer display names, and free-form addresses (landmark + street). Single source of truth for all log writes and LLM-prompt construction. Constitution Principle V.
- [X] T021 [P] [TEST] Implement `tests/infra/test_redaction.py` proving the redaction utility scrubs the formats above on representative inputs (Principle V; constitution §Operational Constraints — PII redaction layer).
- [X] T022 [P] Implement structured JSON logging in `app/infra/logging.py` (python-json-logger formatter) that routes every record through `redaction.redact(...)` and pulls `request_id` from a `ContextVar`. Schema per research.md R11.
- [X] T023 [P] Implement the request-id middleware in `app/api/middleware.py` setting the `ContextVar` on every incoming HTTP request and Telegram update.
- [X] T024 [P] Implement `app/infra/cost_log.py` writing one structured record per LLM/embedding call: `{ts, request_id, provider, model, tier, input_tokens, output_tokens, est_cost_usd, latency_ms}`. Constitution Principle IV; research.md R3.
- [X] T025 Implement the async SQLAlchemy engine + sessionmaker in `app/db/engine.py` (asyncpg driver, pool size sized for v1 single-replica).
- [X] T026 Implement the async Redis client in `app/infra/redis_client.py` and the Redis-only draft + failure-counter store in `app/infra/draft_store.py` (`get`/`put`/`delete`/`incr_failcount`/`reset_failcount`, all with 2-hour TTL on keys `draft:{customer_id}`, `failcount:{customer_id}:{field}`, `chat_state:{customer_id}`). Per data-model.md §OrderDraft, §FailureCounter; research.md R6.
- [X] T027 Implement the intent classifier loader in `app/infra/intent_classifier.py`: load `data/intent_classifier.joblib` once at lifespan startup and expose `classify(text) -> (Intent, confidence)`. Per research.md R5.
- [X] T028 [TEST] Implement the intent classifier CI gate in `tests/golden/intent/test_classifier_threshold.py`: run the frozen held-out evaluation slice and assert `macro_F1 >= 0.93`. Constitution Principle II; research.md R5.
- [X] T029 Define Pydantic domain models in `app/domain/`: `customer.py`, `order.py` (OrderDraft/OrderItem/Customization/ConfirmedOrder), `menu.py` (MenuItem/MenuChunk), `conversation.py` (Conversation/Turn/FailureCounter), `language.py` (Language enum, DetectedLanguage), `errors.py` (`ExternalDependencyError`, `OrderValidationError`, etc.). Per data-model.md.
- [X] T030 [P] Define tool I/O Pydantic models in `app/domain/tools.py` — one input + one output model per tool listed in `contracts/internal_tools.md` (`ParseOrderIn/Out`, `MatchDishIn/Out`, `AnswerMenuQuestionIn/Out`, `ExtractAddressIn/Out`, `CheckZoneIn/Out`, `DetectLanguageIn/Out`, `RenderReadbackIn/Out`, `SummarizeForDispatcherIn/Out`).
- [X] T031 [P] Define external-client `Protocol` interfaces in `app/domain/clients.py` — `LLMClient`, `EmbeddingClient`, `MessengerClient`. Per research.md R14.
- [X] T032 Implement `GroqClient` in `app/infra/groq_client.py` with `complete_mechanical(...)` and `complete_synthesis(...)`, both async, both emitting a cost-log record correlated by `request_id`. Per research.md R3.
- [X] T033 [P] Implement local `EmbedderClient` in `app/infra/embed_client.py` — loads `intfloat/multilingual-e5-large` via sentence-transformers at lifespan startup, exposes `embed_query`/`embed_documents` that offload through `asyncio.to_thread`. Per research.md R2.
- [X] T034 [P] Implement `TelegramClient` in `app/infra/telegram_client.py` (python-telegram-bot v21+ wrapper). Selects polling vs. webhook from `Settings.TELEGRAM_WEBHOOK_URL`. Constant-time secret-path comparison and `X-Telegram-Bot-Api-Secret-Token` header check on the webhook route. Per research.md R4 and `contracts/telegram_webhook.md`.
- [X] T035 Implement SQLAlchemy ORM in `app/db/models.py` for `Customer`, `Address`, `MenuItem`, `MenuChunk` (with `Vector(1024)` column via pgvector), `ConfirmedOrder`, `OrderItem`, `OrderCustomization`, `Conversation`, `Turn`, `DispatcherAction` (incl. `dispatcher_name`), `DeliveryZone`. Per data-model.md.
- [X] T036 [P] Configure Alembic in `alembic/env.py` for async engine + create the initial migration under `alembic/versions/` executing `CREATE EXTENSION IF NOT EXISTS vector;` and the full schema defined by T035. Per research.md R9.
- [X] T037 Implement the FastAPI app skeleton in `app/main.py` (lifespan handler: instantiate `Settings`, open DB pool, open Redis pool, load `IntentClassifier`, load `EmbedderClient`, start `TelegramClient` in selected mode). App refuses to start if `Settings` validation fails. Per plan.md §Project Structure.
- [X] T038 [P] Implement `/healthz` and `/readyz` in `app/api/health.py`. `/readyz` returns 503 until DB, Redis, classifier, and embedder are all ready. Per `contracts/dispatcher_api.openapi.yaml` health paths.
- [X] T039 [P] Implement architecture-layering test in `tests/architecture/test_layering.py` — parses imports under `app/` and asserts: `app/api` imports only from `app/services`, `app/domain`, `app/infra` (not `app/db` or `app/repositories` directly); `app/repositories` does NOT import FastAPI / `HTTPException`; `app/services` does NOT import FastAPI request objects. Constitution Principle I; §Operational Constraints — Layered layout.
- [X] T040 [P] [TEST] Implement async-purity test in `tests/architecture/test_async_purity.py` asserting no `time.sleep` and no `requests` imports under `app/api` or `app/services`. Constitution §Operational Constraints — Async-only request path.
- [X] T041 [P] [TEST] Implement the tier-enforcement test in `tests/services/test_tool_tier_enforcement.py` — for every mechanical-tier tool listed in `contracts/internal_tools.md` §"Tool registry tier assignments", instantiate it with a fake `LLMClient` whose `complete_synthesis` raises, and verify the tool can still complete its job using only `complete_mechanical`; vice versa for synthesis tools. Constitution Principle IV.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — New customer places end-to-end order (Priority: P1) 🎯 MVP

**Goal**: A brand-new customer opens a Telegram chat, sees the welcome + menu, types an order, chooses delivery or pickup (providing an address if delivery), reviews the bot's read-back, presses Confirm, and the order arrives in the dispatcher dashboard where a human marks it as entered in the POS.

**Independent Test**: A tester completes a full delivery order via Telegram (start → menu → order → address → confirm) and verifies the order surfaces in `GET /api/dispatcher/orders` with every FR-020 field, then `POST .../entered-in-pos` transitions it to `entered_in_pos`.

- [X] T042 [US1] Implement `MenuRepository` in `app/repositories/menu_repo.py` — loads `data/menu_full_ar.json` at startup, upserts `menu_items` rows, exposes `get_menu()`, `get_item(id)`, `find_by_phrase(phrase)` (used by the first-pass internal fuzzy lookup of `parse_order`). FR-001, FR-002, FR-005; data-model.md §MenuItem.
- [X] T043 [P] [US1] Implement `ZoneRepository` in `app/repositories/zone_repo.py` — loads `data/restaurant_info.json` `delivery.areas` at startup, strips placeholder entries matching `^\[.*\]$` with a single WARN log carrying the skipped count, upserts `delivery_zones` rows. FR-035; research.md R8; data-model.md §ZoneEntry.
- [X] T044 [P] [US1] Implement `CustomerRepository` in `app/repositories/customer_repo.py` — `find_by_phone_e164`, `create`, `update_last_seen_at`. FR-012, FR-014; data-model.md §Customer.
- [X] T045 [P] [US1] Implement `OrderRepository` in `app/repositories/order_repo.py` for `ConfirmedOrder` writes/reads only (drafts are Redis-only). Includes `create_confirmed`, `get`, `list_awaiting_review`, `apply_edit`, `mark_entered_in_pos`. FR-020, FR-021, FR-022; data-model.md §ConfirmedOrder.
- [X] T046 [P] [US1] Implement `TranscriptRepository` in `app/repositories/transcript_repo.py` appending one `Turn` row per inbound and outbound message. Used by FR-020 (`transcript_url`) and FR-025 (escalation evidence). data-model.md §Conversation+Turn.
- [X] T047 [US1] Implement `LanguageService` in `app/services/language_service.py` — `detect(text) -> DetectedLanguage`, `reply_language(detected) -> Language` enforcing FR-031 (Arabizi input → English reply). FR-028..FR-032.
- [X] T048 [P] [US1] Implement the `detect_language` tool in `app/services/tools/detect_language.py` per `contracts/internal_tools.md` §detect_language — fast script/n-gram heuristic first, mechanical-tier LLM only on ambiguity. FR-028.
- [X] T049 [US1] Implement the `parse_order` tool in `app/services/tools/parse_order.py` per `contracts/internal_tools.md` §parse_order — calls `MenuRepository.find_by_phrase` as the internal fuzzy lookup, places below-threshold phrases into `unresolved` with original text preserved, emits a confidence score. FR-003, FR-005, FR-006.
- [X] T050 [US1] Implement the `match_dish` tool in `app/services/tools/match_dish.py` per `contracts/internal_tools.md` §match_dish — second-pass resolver with alternatives. FR-005.
- [X] T051 [US1] Wire the parse_order → match_dish two-pass pipeline in `app/services/conversation_service.py` per `contracts/internal_tools.md` §parse_order "Pipeline contract" — on each `unresolved` phrase, call `match_dish`; only after both fail prompt the customer for clarification and increment `failcount:{customer_id}:order_parse`. FR-003, FR-005, FR-006.
- [X] T052 [US1] [TEST] Implement `tests/services/test_two_pass_resolution.py` covering: (a) parse_order alone resolves a clean order; (b) ambiguous phrase goes through match_dish and resolves with alternatives; (c) both fail → clarification prompt + counter increment. Internal_tools.md §parse_order Pipeline contract.
- [X] T053 [P] [US1] Implement the `extract_address` tool in `app/services/tools/extract_address.py` per `contracts/internal_tools.md` §extract_address. FR-010.
- [X] T054 [P] [US1] Implement the `check_zone` tool in `app/services/tools/check_zone.py` using rapidfuzz token-set ratio against `ZoneRepository.list_areas()` (threshold ≥80; "not confident → don't warn" per research.md R8). FR-035.
- [X] T055 [US1] Implement `OrderDraftService` in `app/services/order_draft_service.py` against `draft_store` only: `start_draft`, `add_items`, `attach_customization`, `set_fulfillment`, `attach_address` / `attach_location`, `select_saved_address`, `reopen_for_edit` (preserves items, customizations, fulfillment, address — FR-018), `validate_ready_to_confirm` (FR-019 error codes `EMPTY_CART`, `MISSING_FULFILLMENT`, `MISSING_ADDRESS`, `ITEM_UNAVAILABLE`). FR-003, FR-004, FR-009, FR-010, FR-018, FR-019; data-model.md §OrderDraft.
- [X] T056 [US1] Implement the `render_readback` tool in `app/services/tools/render_readback.py` per `contracts/internal_tools.md` §render_readback — accepts a deserialized `OrderDraft` domain model (callers must deserialize from Redis first); returns localized read-back text including the "final pricing is confirmed by the dispatcher" line, plus the inline-keyboard payload with `confirm:<draft_id>` and `edit:<draft_id>` callback data. FR-016.
- [X] T057 [US1] Implement `OrderService` in `app/services/order_service.py` with the only path that mutates POS-relevant state. Methods: `confirm(customer, draft_id)` (creates `ConfirmedOrder`, freezes `items_snapshot` and `address_snapshot`, computes `flags` including `out_of_zone_warning` per FR-035, deletes the Redis draft), `mark_entered_in_pos(order_id, dispatcher_id, dispatcher_name)`, `cancel(order_id, dispatcher_id, dispatcher_name, reason)`. FR-017, FR-020, FR-022, FR-023, FR-035; data-model.md §ConfirmedOrder + OrderState invariants.
- [X] T058 [US1] [TEST] Implement `tests/services/test_pos_transition_invariant.py` asserting `state` only flips to `entered_in_pos` via `OrderService.mark_entered_in_pos`; every other public mutation path leaves `entered_in_pos_at` null. FR-023 invariant; constitution §Operational Constraints — Human confirmation.
- [X] T059 [US1] Implement the Telegram inbound router in `app/api/telegram_router.py` — webhook endpoint at `POST /telegram/webhook/{secret_path}` and polling background task per `contracts/telegram_webhook.md`. Routes `/start` (FR-001), text messages, `message.contact` (FR-014 phone bind), `message.location` (FR-010), and `callback_query` for `confirm:` / `edit:` / `saved_address:` (FR-016, FR-018, FR-013). FR-001, FR-009, FR-010, FR-016, FR-018; contracts/telegram_webhook.md §Update types consumed.
- [X] T060 [US1] Implement `ConversationService.handle_text` in `app/services/conversation_service.py` orchestrating: detect language → record `Turn` → classify intent → route to tool(s) → render reply → record outbound `Turn`. For US1, route `order` intent only; `query` returns a "menu Q&A coming soon" localized stub (filled in by US2). FR-001..FR-019, FR-028..FR-033.
- [X] T061 [P] [US1] Implement `CustomerService` in `app/services/customer_service.py` — `find_by_phone_e164`, `start_new_customer_flow`, `bind_phone_from_contact`, `set_display_name`, `persist_on_confirmation`. FR-012, FR-014.
- [X] T062 [US1] Implement the welcome flow in `ConversationService.on_start` — sends a localized welcome message and the full menu (categories with items underneath) on `/start` and on any first message from an unknown customer. FR-001, FR-002.
- [X] T063 [US1] Implement dispatcher REST surface for orders in `app/api/dispatcher/orders.py`: `GET /api/dispatcher/orders` (with optional `flag` query for `out_of_zone_warning`), `GET /api/dispatcher/orders/{id}`, `PATCH /api/dispatcher/orders/{id}`, `POST /api/dispatcher/orders/{id}/entered-in-pos`, `POST /api/dispatcher/orders/{id}/cancel`. Per `contracts/dispatcher_api.openapi.yaml`. FR-020, FR-021, FR-022, FR-023.
- [X] T064 [US1] Implement bearer-token + `dispatcher_name`-on-mutation auth in `app/api/dispatcher/auth.py`. Reads `Authorization: Bearer ...` against `Settings.DISPATCHER_API_TOKEN`; for any mutation endpoint, validates the `dispatcher_name` body field (non-empty trimmed, ≤80 chars) and returns 400 `DISPATCHER_NAME_REQUIRED` otherwise. Research.md R12; contracts/dispatcher_api.openapi.yaml §DispatcherName.
- [X] T065 [US1] Implement `DispatcherService` in `app/services/dispatcher_service.py` — `list_orders`, `get_order`, `edit_order`, `mark_entered_in_pos`, `cancel`. Every mutation appends a `DispatcherAction` row carrying `dispatcher_id` (token hash) and `dispatcher_name`. FR-021, FR-022, FR-023; research.md R12; data-model.md §DispatcherAction.
- [X] T066 [P] [US1] [TEST] Implement Pydantic schema tests for domain models in `tests/domain/test_order_models.py`, `tests/domain/test_customer_models.py`, `tests/domain/test_address_models.py` covering valid and invalid inputs at every boundary. Constitution Principle II.
- [X] T067 [P] [US1] [TEST] Implement dispatcher request-body tests in `tests/api/test_dispatcher_schemas.py` covering: `dispatcher_name` missing → 400; empty / whitespace-only → 400; >80 chars → 400; valid name passes. Research.md R12; contracts/dispatcher_api.openapi.yaml §DispatcherName.
- [X] T068 [P] [US1] [TEST] Implement transcript test in `tests/services/test_transcript_writes.py` — every customer message and every bot reply lands as a `Turn` row with redacted text, correct `language`, and correct `intent`. FR-020 transcript_url surface; FR-028.
- [X] T069 [US1] Implement graceful degradation per FR-034: when any tool / Groq / Redis / DB raises `ExternalDependencyError`, `ConversationService` returns a localized degradation message offering retry or escalation, and emits a redacted error log. Constitution Principle III §Graceful degradation.
- [X] T070 [US1] [TEST] Implement `tests/services/test_graceful_degradation.py` simulating Groq failure and Redis disconnection, asserting localized degradation messaging and no stack trace surfaces in the reply. FR-034.
- [X] T071 [US1] [TEST] Implement end-to-end happy-path test in `tests/e2e/test_us1_happy_path.py` with `TelegramClient`, `GroqClient`, `EmbedderClient` faked: send `/start` → menu reply, send `2 hummus, 1 fattoush` → parse+pickup→delivery, send `Hamra Street near AUB` → in-zone, press Confirm callback → `GET /api/dispatcher/orders` shows the order with every FR-020 field, `POST .../entered-in-pos` with `dispatcher_name` → state flips. Constitution Principle II §end-to-end test.

**Checkpoint**: At this point, US1 is fully functional end-to-end. The MVP can be demoed.

---

## Phase 4: User Story 2 — Menu Q&A in conversation (Priority: P2)

**Goal**: A customer can ask natural-language menu questions (ingredients, spice, portion, price) and the bot answers from the corpus, then continues building the same order without restarting.

**Independent Test**: Starting from a working US1 flow, a tester asks 3–5 menu questions of different types in a single conversation, then completes an order. Each answer must come from the corpus, and the post-Q&A order must complete and reach the dispatcher.

- [X] T072 [US2] Implement the menu chunking + embedding pipeline as a one-off CLI in `app/cli/embed_menu.py`: for each menu item, build per-language chunks (en, ar), call `EmbedderClient.embed_documents`, write `MenuChunk` rows via the menu repository. Idempotent (upsert keyed by `(menu_item_id, language)`). Per data-model.md §MenuChunk and research.md R2.
- [X] T073 [US2] Implement `MenuService.search(query: str, k: int = 3)` in `app/services/menu_service.py` — embed query via `EmbedderClient.embed_query`, run `SELECT ... ORDER BY embedding <-> :q LIMIT k` against pgvector. FR-007.
- [X] T074 [US2] Implement the `answer_menu_question` tool in `app/services/tools/answer_menu_question.py` per `contracts/internal_tools.md` §answer_menu_question — retrieve via `MenuService.search`, call `GroqClient.complete_synthesis` with a "only answer from citations" prompt, return `{answer, citations}`. Returns `{answer: "I don't have info on that — let me show you what we do have.", citations: []}` when retrieval is empty. FR-007.
- [X] T075 [US2] Wire menu Q&A into `ConversationService`: when the classifier returns `query` intent, route to `answer_menu_question`, preserve the active `OrderDraft` across the turn (Q&A and order building share one conversation). FR-008.
- [X] T076 [US2] [TEST] Build the RAG golden set at `tests/golden/rag/dataset.jsonl` containing 10–15 questions covering ingredients, price, spice, portion in three languages: English, Lebanese Arabic, Arabizi. Each line: `{question, language, expected_top_menu_item_ids}`. Research.md R2 validation plan.
- [X] T077 [US2] [TEST] Implement RAG retrieval threshold test in `tests/golden/rag/test_retrieval_threshold.py` — runs `MenuService.search` on every golden question and asserts hit@3 ≥ 0.8. Constitution Principle II; research.md R2.
- [X] T078 [US2] [TEST] Implement `tests/services/test_no_fabrication.py` asserting that for a dish absent from the menu, `answer_menu_question` returns the no-info reply with empty `citations` and never invents ingredients/prices/spice. FR-007.
- [X] T079 [US2] [TEST] Implement `tests/services/test_qa_preserves_draft.py` — start a draft (US1 path), ask a menu question, add another item, confirm; the final order contains both pre-Q&A and post-Q&A items. FR-008.

**Checkpoint**: US1 + US2 work independently. Customers can ask questions while ordering.

---

## Phase 5: User Story 3 — Customizations (Priority: P2)

**Goal**: A customer can attach modifiers, removals, cooking preferences, and extras to any item; the bot captures them on the parent item, surfaces them in the read-back and in the dispatcher view, and refuses to silently drop unmappable customizations.

**Independent Test**: From a working US1 flow, place an order with at least three different customizations across different items. Each customization must appear under the correct item in both the customer's read-back and the dispatcher's view.

- [X] T080 [US3] Extend `parse_order` (T049) in `app/services/tools/parse_order.py` to recognize and attach modifiers/removals/cook_pref/extra_side/other to the parent item per data-model.md §Customization. FR-004.
- [X] T081 [US3] Extend `render_readback` (T056) so each customization appears under its parent item in the read-back text. FR-016 wording.
- [X] T082 [US3] Extend `OrderRepository.create_confirmed` (T045) so `OrderItem.customizations` persist on the confirmed order and surface in `OrderDetail.items[].customizations` of the dispatcher API. FR-020; contracts/dispatcher_api.openapi.yaml §OrderItem.
- [X] T083 [US3] [TEST] Implement `tests/services/test_readback_customizations.py` covering three customization kinds attached to two different items, asserting placement under parents in the read-back. FR-016.
- [X] T084 [US3] [TEST] Implement `tests/api/test_dispatcher_customizations.py` calling `GET /api/dispatcher/orders/{id}` and asserting every customization is present under its parent item. FR-020.
- [X] T085 [US3] [TEST] Implement `tests/services/test_unmapped_customization.py` — send a deliberately unmappable customization, assert the bot asks for clarification and does NOT silently drop the customization. FR-006.

**Checkpoint**: US1 + US2 + US3 work independently. Customers can order with full customization fidelity.

---

## Phase 6: User Story 4 — Returning customer recognition (Priority: P3)

**Goal**: A customer who has ordered before is greeted by name and offered their saved address(es) as inline one-tap choices when ordering delivery.

**Independent Test**: Place a first order (saving phone, name, address). End the chat. Reopen the chat. The bot must greet by name and offer the saved address; tapping it must let the customer complete a new order without re-typing personal details.

- [X] T086 [US4] Extend `CustomerService` (T061) with `find_by_phone_e164` lookup on the customer's Telegram-shared phone, used by `ConversationService.on_start` to greet returning customers by name. FR-012; data-model.md §Customer.
- [X] T087 [US4] Implement saved-address inline keyboard rendering: when a returning customer chooses delivery, render one inline button per saved `Address` plus a `🆕 New address` button. Wired into the Telegram router's callback handler under `saved_address:<address_id>`. FR-013; contracts/telegram_webhook.md §Inline keyboards — saved_addresses.
- [X] T088 [US4] Implement "use a different address" path in `OrderDraftService.attach_address`: a fresh address saves a new `Address` row alongside the customer's existing addresses. FR-015.
- [X] T089 [US4] Implement profile persistence in `OrderService.confirm` (T057): on a new customer's first confirmation, persist `phone_e164`, `display_name`, and (for delivery) the `Address`. FR-014.
- [X] T090 [US4] [TEST] Implement `tests/e2e/test_us4_returning_customer.py` — first order saves profile; second chat greets by name and offers the saved address with a one-tap callback; second order completes using the saved address. FR-012, FR-013, FR-014, FR-015.

**Checkpoint**: Returning customers get the recognition shortcut. US1–US4 each remain independently testable.

---

## Phase 7: User Story 5 — Escalation to a human handler (Priority: P3)

**Goal**: After three consecutive failures on the same field, the bot stops trying autonomously, posts the chat to the dispatcher's needs-human queue with the full transcript, and routes the conversation through the dispatcher until close-handoff.

**Independent Test**: Send three consecutive messages on the same field that the bot cannot resolve. On the third, the chat must appear in `GET /api/dispatcher/escalations` with full transcript; a `POST .../messages` from the dashboard must arrive at the customer's Telegram chat, attributed as coming from a human operator; `POST .../close-handoff` must return control to the bot.

- [X] T091 [US5] Extend `draft_store` (T026) with failure-counter operations: `incr_failcount(customer_id, field)`, `reset_failcount(customer_id, field)`, `get_failcount(customer_id, field)`, keyed by `failcount:{customer_id}:{field}` with 2-hour TTL. Fields: `order_parse`, `dish_match`, `address_extract`. FR-024; data-model.md §FailureCounter.
- [X] T092 [US5] Implement `EscalationService` in `app/services/escalation_service.py` — `register_failure(customer_id, field)` increments the counter and on the third consecutive failure sets `Conversation.awaiting_human = true`, snapshots the transcript pointer, and enqueues a `dispatcher_notify` RQ job. `close_handoff` clears the flag and resets counters. FR-024, FR-025.
- [X] T093 [US5] Implement the `summarize_for_dispatcher` tool in `app/services/tools/summarize_for_dispatcher.py` per `contracts/internal_tools.md` §summarize_for_dispatcher — synthesis-tier call that produces the one-line `active_draft_summary` string used in `EscalationSummary` per contracts/dispatcher_api.openapi.yaml §EscalationSummary. FR-025.
- [X] T094 [US5] Implement dispatcher REST for escalations in `app/api/dispatcher/escalations.py`: `GET /api/dispatcher/escalations`, `GET /api/dispatcher/escalations/{id}`, `POST .../take-over`, `POST .../messages`, `POST .../close-handoff`. All mutations require `dispatcher_name`. Per `contracts/dispatcher_api.openapi.yaml`. FR-025, FR-026; research.md R12.
- [X] T095 [US5] Implement the dispatcher↔customer message bridge: while `Conversation.awaiting_human = true`, `ConversationService.handle_text` forwards inbound customer messages to the dispatcher view (no bot reply); `DispatcherService.send_message` posts the dispatcher's text back to the customer's Telegram chat via `TelegramClient.send_message`, prefixed with a localized human-operator attribution line, and persists a `Turn(sender="dispatcher")`. FR-026; contracts/dispatcher_api.openapi.yaml §POST .../messages.
- [X] T096 [US5] [TEST] Implement `tests/services/test_no_callout_prompts.py` — scans `app/prompts/**` and asserts no template instructs the customer to call a phone number, leave the channel, or abandon the conversation. FR-027.
- [X] T097 [US5] Implement `EscalationDetail.active_draft` mapping: convert the active Redis draft (if any) into the `DraftSummary` shape per contracts/dispatcher_api.openapi.yaml §DraftSummary (Redis snapshot, no order state, no dispatcher_actions). FR-025; contracts/dispatcher_api.openapi.yaml §EscalationDetail.
- [X] T098 [US5] [TEST] Implement `tests/e2e/test_us5_escalation.py` — three consecutive `address_extract` failures → chat appears in escalation queue with transcript and active_draft DraftSummary → dispatcher take-over → dispatcher messages reach the customer's chat → close-handoff returns control to the bot, counters reset. FR-024..FR-027.
- [X] T099 [P] [US5] Implement RQ worker jobs in `app/workers/jobs.py`: `draft_expiration_sweep` (clears `Conversation.active_draft_id` for any conversation whose Redis draft has expired), `dispatcher_notify` (publishes a notification event into the dispatcher queue surface). Per plan.md §Project Structure.

**Checkpoint**: All five user stories now functional and independently testable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, decision records, final cross-cutting verification.

- [ ] T100 [P] Flesh out `DECISIONS.md` with full rationale paragraphs for each of the ten architecture decisions (one paragraph per entry, with evidence collected during implementation). Constitution Principle VI.
- [ ] T101 [P] Flesh out `ARCH.md` with: layered-architecture diagram, request lifecycle for a Telegram update, request lifecycle for a dispatcher REST call, data-flow for `OrderDraft → ConfirmedOrder`, escalation flow. Constitution Principle VI.
- [ ] T102 [P] Flesh out `RUNBOOK.md` with the operational procedures listed in T015, fully written. Constitution Principle VI.
- [ ] T103 [P] Flesh out `README.md` as the 5-minute setup pointing operators to `quickstart.md` for the deeper walkthrough. Constitution Principle VI.
- [ ] T104 Run the `quickstart.md` US1 walkthrough end-to-end against the running `docker compose` stack, then run the multilingual smoke check and the FR-034 failure-path smoke checks. Update tasks or contracts for any gap surfaced. Per `quickstart.md`.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user-story phases.
- **User Story phases (Phases 3–7)**: Each depends on Foundational. After Foundational lands, US1 → US2 → US3 → US4 → US5 in the user-supplied priority order; US2, US3, US4, US5 can be developed in parallel by different developers once Foundational is in.
- **Polish (Phase 8)**: Depends on all stories that the team intends to ship.

### User story dependencies

- **US1 (P1)**: Depends only on Foundational. Independent of US2–US5.
- **US2 (P2)**: Depends on Foundational. Touches `ConversationService` (T060) for routing; the menu-Q&A intent path is a clean extension, not a rewrite.
- **US3 (P2)**: Extends US1 surfaces (`parse_order`, `render_readback`, `OrderRepository`). Soft dependency on US1 being merged; can be developed against the US1 branch.
- **US4 (P3)**: Extends `CustomerService`, `OrderDraftService`, and the Telegram router. Soft dependency on US1.
- **US5 (P3)**: Extends `draft_store`, `ConversationService`, and the dispatcher API surface. Soft dependency on US1.

### Within each user story

- Repositories before services.
- Tools before the conversation service that calls them.
- Services before HTTP endpoints.
- Domain tests in parallel with implementation.
- E2E test last in each story.

### Parallel opportunities

- **Phase 1**: T002, T003, T004, T005, T006, T007, T008, T009, T013, T014, T015, T016, T017 — independent files.
- **Phase 2**: T020/T021, T022, T023, T024 are independent; T030, T031, T033, T034 are independent of each other; T038, T039, T040, T041 are independent test scaffolds.
- **Phase 3 (US1)**: T043, T044, T045, T046, T048, T053, T054, T061 are parallelizable [P] within the story.
- **Phase 5 (US3)**: All test tasks (T083, T084, T085) parallel after T080–T082 land.
- **Phase 7 (US5)**: T099 (RQ worker) parallel with the dispatcher REST work.
- **Phase 8**: All polish tasks except T104 are independent.

---

## Implementation Strategy

### MVP first (US1 only)

1. Finish Phase 1: Setup.
2. Finish Phase 2: Foundational (CRITICAL — blocks all stories).
3. Finish Phase 3: US1.
4. **STOP and VALIDATE**: walk through `quickstart.md` US1 happy path; run `tests/e2e/test_us1_happy_path.py`. The MVP is shippable.

### Incremental delivery

1. Setup + Foundational → foundation ready.
2. Add US1 → demo MVP.
3. Add US2 → menu Q&A.
4. Add US3 → customizations.
5. Add US4 → returning-customer shortcut.
6. Add US5 → human-in-the-loop escalation.
7. Polish.

Each story is shippable on its own.

### Parallel team strategy

Once Foundational lands, three developers can split:

- Dev A: US1 (T042–T071) — owns the MVP.
- Dev B: US2 (T072–T079) once US1's `ConversationService` shape is stable.
- Dev C: US3 + US4 — Customizations and returning-customer flows.
- Dev D (or whoever frees up): US5 — Escalation.

---

## Notes

- `[P]` tasks operate on different files and have no incomplete dependencies.
- `[Story]` labels map a task to a user-story phase for traceability.
- Each user story is independently completable and testable per the Independent Test criterion at the top of its phase.
- Per the constitution: no `time.sleep`, no `requests` anywhere in `app/api` / `app/services`; PII is redacted at log/LLM-prompt boundaries; LLM tier discipline (mechanical vs. synthesis) is enforced by T041.
- Commit after each task or logical group (the project's git-extension hook offers `/speckit-git-commit` for this).
- The frontend dispatcher dashboard is OUT OF SCOPE for this feature per plan.md §Structure Decision and research.md R13. All dispatcher-facing surfaces here are HTTP endpoints; the React UI is generated by Stitch from `contracts/dispatcher_api.openapi.yaml` in a later phase.
