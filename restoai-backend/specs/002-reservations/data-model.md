# Phase 1 Data Model: Telegram Table Reservations

**Feature**: `002-reservations` | **Date**: 2026-06-13

This document specifies the new and modified entities introduced by the
reservations feature, their fields, relationships, validation rules, and
state transitions. Entities exist in three forms that MUST stay aligned:

- **Pydantic domain model** in `app/domain/` — used at every external
  boundary (HTTP, LLM tool input/output, Telegram callback payloads).
- **SQLAlchemy ORM** in `app/db/models.py` — persistence representation,
  imported only by `app/repositories/`.
- **Redis structures** — ephemeral state with TTL (reservation drafts,
  chat state collected in turn-by-turn flow).

Field types below use Python type hints; the SQLAlchemy column type is
shown in parentheses where it differs.

---

## Unchanged entities from 001

`Customer`, `Address`, `Conversation`, `Turn`, `FailureCounter`,
`MenuItem`, `MenuChunk`, `DeliveryZone`, `DispatcherAction`,
`ConfirmedOrder`, `OrderDraft` — all unchanged. No 001 table or domain
model is modified by this feature.

---

## New value object: SeatingPreference

**Storage**: Python `StrEnum`; stored as `varchar(24)` in the
`reservations` table column `seating_preference`.

**Spec mapping**: FR-003, FR-004, FR-005, FR-006, FR-015, FR-016b.

```python
class SeatingPreference(StrEnum):
    INDOOR_SMOKING     = "indoor_smoking"
    INDOOR_NON_SMOKING = "indoor_non_smoking"
    OUTDOOR_TERRACE    = "outdoor_terrace"
    OUTDOOR_NON_TERRACE = "outdoor_non_terrace"
```

**Terrace rule** (FR-006): `SeatingPreference.OUTDOOR_TERRACE` is only
valid when `party_size <= 5`. Any other value has no size constraint
(beyond the > 14 call-center rule, FR-007).

---

## New entity: ReservationDraft

**Storage**: Redis-only. Key `res_draft:{customer_id}` as a JSON blob
with 2-hour TTL (same `DRAFT_TTL` constant as `OrderDraft`). No Postgres
mirror; the first durable artifact is the confirmed `Reservation` row
(research.md R1).

**Spec mapping**: Spec §Key Entities — ReservationDraft; FR-001, FR-002,
FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | New per draft session. |
| `customer_id` | `UUID` | Owning customer. |
| `date` | `date \| None` | ISO-8601 date; `None` until collected. |
| `time` | `time \| None` | ISO-8601 time (24h); `None` until collected. |
| `party_size` | `int \| None` | 1–14; `None` until collected. |
| `name` | `str \| None` | Customer name for the booking; pre-filled from `Customer.display_name` if known. |
| `phone` | `str \| None` | E.164 phone; pre-filled from `Customer.phone_e164` if known. |
| `seating_preference` | `SeatingPreference \| None` | `None` until seating dialog completes. |
| `language` | `Language` | Last detected conversation language. |
| `created_at` | `datetime` | Draft creation timestamp. |
| `updated_at` | `datetime` | Refreshed on every field update; drives TTL reset. |

**Validation rules** (enforced in `ReservationService.validate_ready_to_confirm`):

- `date is not None` and `date >= today()` — else `MISSING_DATE` /
  `PAST_DATE`. FR-008.
- `time is not None` — else `MISSING_TIME`.
- `party_size is not None and 1 <= party_size <= 14` — else
  `MISSING_PARTY_SIZE` / `PARTY_TOO_LARGE`. FR-007 check is applied
  earlier (at collection time), not just at confirm.
- `name is not None and len(name.strip()) >= 1` — else `MISSING_NAME`.
- `phone is not None` and matches E.164 pattern — else `MISSING_PHONE`.
- `seating_preference is not None` — else `MISSING_SEATING`.
- When `seating_preference == OUTDOOR_TERRACE`, `party_size <= 5` —
  else `TERRACE_TOO_LARGE`. FR-006.

---

## New entity: Reservation

**Storage**: Postgres `reservations` table. Mutable only via the
`ReservationService` methods.

**Spec mapping**: Spec §Key Entities — Reservation; FR-010, FR-011,
FR-012, FR-013, FR-014, FR-015, FR-016, FR-016b, FR-017, FR-018,
FR-019, FR-025.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` (uuid, PK) | Internal surrogate key. |
| `reference` | `str` (varchar(12), unique, indexed) | `RES-XXXXXXX` human-readable reference; research.md R3. |
| `customer_id` | `UUID` (FK customers.id, indexed) |  |
| `date` | `date` (date) |  |
| `time` | `time` (time without time zone) |  |
| `party_size` | `int` (smallint) | 1–14. |
| `name` | `str` (varchar(120)) | Booking name, not necessarily `Customer.display_name`. |
| `phone` | `str` (varchar(20)) | E.164 phone on the booking. |
| `seating_preference` | `str` (varchar(24)) | `SeatingPreference` value. |
| `state` | `str` (varchar(16), indexed) | `ReservationState` value; see state machine below. |
| `language` | `str` (varchar(16)) | Language of the conversation at confirmation. |
| `created_at` | `datetime` (timestamptz) |  |
| `updated_at` | `datetime` (timestamptz) |  |
| `cancelled_at` | `datetime \| None` (timestamptz) | Set when state transitions to `cancelled`. |

**Relationships**: N..1 `Customer`.

**PII redaction**: `name`, `phone` MUST go through `redaction.redact(...)`
before logging.

### ReservationState — state machine

```
active
  │
  ├─── modify (date / time / party_size / seating) ───►  active   (idempotent)
  │
  └─── cancel ───►  cancelled   (terminal)
```

**Invariants** (Principle III):

- `state` can only transition to `cancelled` via
  `ReservationService.cancel(reservation_id, customer_id)` after
  explicit customer confirmation (FR-018). Asserted by unit test.
- A `Reservation` row MUST NOT exist without a completed seating dialog
  and every required field present. Enforced by
  `validate_ready_to_confirm` being the sole code path to
  `reservation_repo.create(...)`.

---

## New value object: ReservationValidationCode

**Spec mapping**: FR-006, FR-007, FR-008, and validation gate.

```python
class ReservationValidationCode(StrEnum):
    MISSING_DATE      = "missing_date"
    PAST_DATE         = "past_date"
    MISSING_TIME      = "missing_time"
    MISSING_PARTY_SIZE = "missing_party_size"
    PARTY_TOO_LARGE   = "party_too_large"
    MISSING_NAME      = "missing_name"
    MISSING_PHONE     = "missing_phone"
    MISSING_SEATING   = "missing_seating"
    TERRACE_TOO_LARGE = "terrace_too_large"
```

Raised as `ReservationValidationError(code, detail=...)` by the service
layer; caught by the Telegram router to present a localized message.

---

## New Redis structures

Managed by `app/infra/reservation_draft_store.py` (research.md R10).

| Key | Type | TTL | Notes |
|---|---|---|---|
| `res_draft:{customer_id}` | JSON blob | 2h | The `ReservationDraft` Pydantic model serialized. Deleted on confirmation or cancellation. |

The `chat_state:{customer_id}` key already exists in `draft_store.py` and
is reused. When collecting reservation fields, the `waiting_for` field
holds values like `"reservation_date"`, `"reservation_time"`,
`"reservation_party_size"`, `"reservation_name"`, `"reservation_phone"`,
`"reservation_seating_indoor"`, `"reservation_seating_outdoor_terrace"`,
or `"reservation_seating_confirm"`.

---

## Alembic migration: 002_reservations_schema.py

One new migration. No changes to existing tables.

```sql
CREATE TABLE reservations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference       VARCHAR(12) NOT NULL UNIQUE,
    customer_id     UUID NOT NULL REFERENCES customers(id),
    date            DATE NOT NULL,
    time            TIME WITHOUT TIME ZONE NOT NULL,
    party_size      SMALLINT NOT NULL,
    name            VARCHAR(120) NOT NULL,
    phone           VARCHAR(20) NOT NULL,
    seating_preference VARCHAR(24) NOT NULL,
    state           VARCHAR(16) NOT NULL DEFAULT 'active',
    language        VARCHAR(16) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at    TIMESTAMPTZ
);

CREATE INDEX ix_reservations_customer_id ON reservations(customer_id);
CREATE INDEX ix_reservations_state ON reservations(state);
CREATE INDEX ix_reservations_reference ON reservations(reference);
CREATE INDEX ix_reservations_date ON reservations(date);
```

---

## Entity-to-FR traceability

| FR | Entity / field touched |
|---|---|
| FR-001 | Conversation Turn (intent detected → reservation flow started) |
| FR-002 | ReservationDraft — all required fields collected |
| FR-003 | ReservationDraft.seating_preference ask (after other fields) |
| FR-004 | SeatingPreference enum — indoor branch |
| FR-005 | SeatingPreference enum — outdoor branch |
| FR-006 | ReservationValidationCode.TERRACE_TOO_LARGE; seating dialog block |
| FR-007 | ReservationValidationCode.PARTY_TOO_LARGE; no draft created |
| FR-008 | ReservationValidationCode.PAST_DATE |
| FR-009 | extract_reservation_fields tool → date read-back confirmation |
| FR-010 | Reservation created, reference generated |
| FR-011 | Reservation — all required fields in confirmation message |
| FR-012 | Reservation.reference (unique, preserved on modify) |
| FR-013 | Reservation partial UPDATE (date / time / party_size / seating) |
| FR-014 | ReservationRepository.find_active_by_customer_phone_e164 |
| FR-015 | SeatingPreference re-validation when party_size changes |
| FR-016 | Re-confirmation message after successful modification |
| FR-016b | SeatingPreference re-ask flow on direct seating change request |
| FR-017 | ReservationService.cancel + customer confirmation gate |
| FR-018 | Cancel inline buttons (Yes/No) before state transition |
| FR-019 | Reservation.state = cancelled + acknowledged in message |
| FR-020 | Turn.language per turn (existing) |
| FR-021 | Existing Language enum + reply_language() (existing) |
| FR-022 | Existing Language enum — AR_LB path (existing) |
| FR-023 | Existing Language enum — ARABIZI path (existing) |
| FR-024 | Existing language switching on next turn (existing) |
| FR-025 | Reservation.language |
| FR-026 | ExternalDependencyError → localized degradation (existing pattern) |
