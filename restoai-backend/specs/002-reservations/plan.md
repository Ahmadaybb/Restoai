# Implementation Plan: Telegram Table Reservations

**Branch**: `002-reservations` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-reservations/spec.md`

## Summary

RestoAI's second feature adds table reservations for Lakkis Farm through
the same Telegram bot already handling takeaway orders. Customers interact
with the bot in English, Lebanese Arabic, or Arabizi to book a table,
choosing a date, time, party size, name, phone number, and seating
preference (indoor smoking/non-smoking or outdoor terrace/non-terrace).
The bot confirms immediately with a unique reference number; no dispatcher
review step exists. Customers can later cancel or modify (date, time, party
size, seating) through the same chat. The design reuses the entire 001
infrastructure — same FastAPI app, same Redis, same Postgres, same Groq
two-tier LLM pattern — and adds one new Postgres table, one new Redis
draft store module, two new tools, one new service, one new repository,
and a new intent handler branch in `conversation_service`.

## Technical Context

**Language/Version**: Python 3.11 (same as 001).

**Primary Dependencies**: No new dependencies. All packages are already
present: FastAPI, Pydantic 2, SQLAlchemy 2.x async + asyncpg, Alembic,
redis-py async, python-telegram-bot, groq SDK, python-json-logger.

**Storage**:
- Postgres `reservations` table (new; one Alembic migration).
- Redis key `res_draft:{customer_id}` for `ReservationDraft` (new key
  prefix; existing `DRAFT_TTL = 7200 s`). No new Redis instance.
- Existing `chat_state:{customer_id}` key reused for turn-by-turn field
  collection (`waiting_for` field).

**Testing**: pytest + pytest-asyncio. Same structure as 001. New test
directories: `tests/domain/`, `tests/services/test_reservation_*.py`,
`tests/e2e/test_us1_reservation_happy_path.py`. All externals mocked.

**Performance Goals**: Same as 001. A reservation turn (text in → reply
out) should complete within the existing 3s/6s p95 budget for mechanical/
synthesis paths respectively.

**Constraints**: No new external dependencies. Async-only request path.
PII (`name`, `phone`) through `app/infra/redaction.py` at every log and
LLM prompt site. Secrets (none new) at startup. Call center number read
from `data/restaurant_info.json`, not hardcoded.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-evaluated after Phase 1
design.*

### Principle I — Clean Architecture & Code Quality

- ✅ New code follows the same `app/{api,services,repositories,domain,
  infra}` layering as 001. The new reservation handler additions in
  `telegram_router.py` call `reservation_draft_service` only. The new
  `ReservationRepository` executes SQL only and never raises HTTP errors.
  `ReservationService` owns transaction boundaries.
- ✅ Two new Pydantic domain models added to `app/domain/`:
  `ReservationDraft` and `Reservation` (plus `SeatingPreference` enum
  and `ReservationValidationCode`). Two new tool input/output models
  added to `app/domain/tools.py`.
- ✅ Two new LLM tools in `app/services/tools/`:
  `extract_reservation_fields.py` and
  `render_reservation_confirmation.py`. Each is a single-responsibility
  module, consistent with existing tool modules.
- ✅ Type hints everywhere; mypy runs on all new modules in CI.

### Principle II — Testing Standards & ML Evaluation Discipline

- ✅ `extract_reservation_fields` tool unit-tested in isolation with
  mocked Groq.
- ✅ `render_reservation_confirmation` tool unit-tested in isolation.
- ✅ `ReservationDraftService.validate_ready_to_confirm` tested with
  every `ReservationValidationCode` path (one parametrized test per
  code).
- ✅ `ReservationService.confirm`, `.modify`, `.cancel` tested with
  mocked repository.
- ✅ Seating rules tested: terrace block (party > 5) and call-center
  redirect (party > 14) each have dedicated unit tests.
- ✅ E2E happy path test: `tests/e2e/test_us1_reservation_happy_path.py`
  covers the full US1 flow with all externals mocked.
- ✅ No new ML model; no golden set required. The intent classifier
  already has `RESERVATION` in its label set (confirmed by inspection of
  `app/domain/language.py`).

### Principle III — Multilingual, Human-in-the-Loop UX

- ✅ Multilingual-first: all localized strings (prompts for each
  collection step, confirmation message, cancel confirmation, call
  center redirect, error messages) are written in EN and AR_LB from
  the first commit. Arabizi is understood via the existing language
  detector (input → English reply).
- ✅ High-stakes action (cancellation) has an explicit Yes/No
  confirmation gate (FR-018) — satisfies "human confirms before the
  AI commits the side effect" for the cancellation path.
- ✅ Graceful degradation: the existing `ExternalDependencyError` pattern
  in `conversation_service` covers all new async calls (Groq, Redis,
  Postgres). No stack traces reach the Telegram chat.

### Principle IV — Performance & Cost Discipline

- ✅ `extract_reservation_fields` uses the mechanical tier (cheap model).
  `render_reservation_confirmation` uses the synthesis tier (stronger
  model). Pattern matches existing `parse_order` / `render_readback`
  split.
- ✅ Cost logging: every new LLM call emits a structured record via
  `app/infra/cost_log.py` — no new cost-log plumbing needed.
- ✅ `restaurant_info.json` (call center number) is loaded once and
  LRU-cached at startup. No per-request file reads.
- ✅ Async throughout. No blocking I/O in the new code paths.

### Principle V — Security & Data Integrity

- ✅ No new required secrets. No new external API keys.
- ✅ PII: `name` and `phone` on `Reservation` and `ReservationDraft`
  MUST be redacted before logging and before LLM prompts. Enforced
  at every new site via `redaction.redact(...)`.
- ✅ `ReservationValidationError` prevents a `Reservation` row from
  being created without all required fields and a valid seating
  choice.

### Principle VI — Documentation as a First-Class Deliverable

- ✅ `DECISIONS.md` updated with four new ADR entries (ADR-011 through
  ADR-014) in the same PR that introduces this feature.
- ✅ `research.md`, `data-model.md`, `quickstart.md`, and `contracts/`
  are the Phase 0/1 artifacts for this feature.
- ✅ Every design decision is justified in `research.md` with explicit
  rationale and alternatives considered.

### Operational Constraints

| Constraint | How satisfied |
|---|---|
| Layered layout | New code in `app/api`, `app/services`, `app/repositories`, `app/domain`, `app/infra`. Cross-layer imports flow inward only. |
| Boundary types | `ReservationDraft`, `Reservation`, `ExtractReservationFieldsIn/Out`, `RenderReservationConfirmationIn/Out`, `ReservationValidationError` are Pydantic models or typed enums. |
| Async-only request path | All new repository, service, and tool calls are async. No new synchronous I/O. |
| Secrets at startup | No new secrets. Existing `Settings` validation unchanged. |
| PII redaction layer | `name` and `phone` pass through `redaction.redact(...)` at all log and LLM prompt sites. Two assertions added to `tests/infra/test_redaction.py`. |
| Cost logging | Both new tool calls emit cost records via `app/infra/cost_log.py`. |
| Human confirmation | Cancellation gated by inline Yes/No buttons (FR-018). Reservation confirmation is immediate — documented deviation ADR-011. |

**HITL deviation**: Immediate reservation confirmation (no dispatcher
review) is a documented deviation from Principle III. Justification:
restaurant owner's explicit requirement; no money changes hands; the
restaurant reviews bookings manually. Recorded in `DECISIONS.md` ADR-011
per constitution §Governance/Deviations.

**Gate result**: ✅ All principles satisfied. One documented deviation
(ADR-011). No unjustified violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-reservations/
├── plan.md               # This file
├── research.md           # Phase 0 output — all design decisions
├── data-model.md         # Phase 1 output — entities and Alembic DDL
├── quickstart.md         # Phase 1 output — validation scenarios
├── contracts/
│   ├── telegram-callbacks.md   # Inline button callback_data strings
│   └── tool-schemas.md         # LLM tool Pydantic schemas
└── tasks.md              # Phase 2 output (/speckit-tasks)
```

### Source Code — new files

```text
app/
├── domain/
│   └── reservation.py          # ReservationDraft, Reservation, SeatingPreference,
│                               #   ReservationState, ReservationValidationCode/Error
├── infra/
│   └── reservation_draft_store.py  # Redis get/put/delete for res_draft:{customer_id}
├── services/
│   ├── reservation_draft_service.py  # collect_field, validate_ready_to_confirm
│   ├── reservation_service.py        # confirm, modify, cancel
│   └── tools/
│       ├── extract_reservation_fields.py
│       └── render_reservation_confirmation.py
├── repositories/
│   └── reservation_repo.py     # create, get, find_active_by_customer, update, cancel
├── prompts/
│   ├── en/
│   │   ├── extract_reservation_fields.txt
│   │   └── render_reservation_confirmation.txt
│   └── ar_lb/
│       ├── extract_reservation_fields.txt
│       └── render_reservation_confirmation.txt
alembic/versions/
└── 002_reservations_schema.py
tests/
├── domain/
│   └── test_reservation.py
├── services/
│   ├── test_reservation_draft_service.py
│   ├── test_reservation_service.py
│   └── test_seating_rules.py
└── e2e/
    └── test_us1_reservation_happy_path.py
```

### Source Code — modified files

```text
app/
├── api/
│   └── telegram_router.py        # Add reservation callback handlers;
│                                 #   add _handle_reservation_intent call
├── services/
│   └── conversation_service.py   # Add Intent.RESERVATION branch
├── db/
│   └── models.py                 # Add Reservation ORM model
├── domain/
│   └── tools.py                  # Add tool schemas for reservation tools
DECISIONS.md                      # Append ADR-011 through ADR-014
```

## Architecture decisions to record

New `DECISIONS.md` entries for the first PR of this feature:

11. **ADR-011 — Immediate reservation confirmation (no dispatcher review)**:
    Reservations are confirmed immediately. Justification: no money changes
    hands; restaurant owner's explicit requirement; manual daily review
    by staff. Principle III HITL deviation — documented per constitution
    §Governance/Deviations.

12. **ADR-012 — Redis-only ReservationDraft (key prefix `res_draft:`)**: Same
    rationale as ADR-007 (order drafts). Separate key prefix and separate
    module to avoid coupling the two draft stores.

13. **ADR-013 — SeatingPreference as typed enum (4 values)**: The spec defines
    exactly four valid seating states. Typed enum at domain boundary enforces
    exhaustiveness and makes the terrace rule a clean comparison.

14. **ADR-014 — Call center number from `restaurant_info.json`**: Restaurant-
    specific content belongs in the data file. `restaurant.contact.phone`
    (`"1661"`) is LRU-cached at startup; no hardcoding, no env-var.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| HITL: immediate confirmation | Restaurant owner's explicit requirement; no money at risk | Dispatcher review adds latency with no practical safety benefit for reservations at this operational scale |

One documented deviation (ADR-011). No other violations.
