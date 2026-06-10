# Phase 1 Data Model: Telegram Takeaway Ordering

**Feature**: `001-takeaway-orders` | **Date**: 2026-06-10

This document specifies the entities, their fields, relationships,
validation rules, and state transitions. Entities exist in three forms
that MUST stay aligned:

- **Pydantic domain model** in `app/domain/` — used at every external
  boundary (HTTP, LLM, tool input/output).
- **SQLAlchemy ORM** in `app/db/models.py` — persistence representation,
  imported only by `app/repositories/`.
- **Redis structures** — ephemeral state with TTL (drafts, failure
  counters, chat state).

Field types below use Python type hints; the SQLAlchemy column type is
shown in parentheses where it differs.

---

## Entity: Customer

**Storage**: Postgres `customers` table.

**Spec mapping**: Spec §Key Entities — Customer; FR-012, FR-014, FR-015.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` (uuid) | PK, generated server-side. |
| `phone_e164` | `str` (varchar(20), unique, indexed) | The Telegram-shared phone in E.164 (`+9613XXXXXXX`). Sole identity. |
| `telegram_user_id` | `int` (bigint, unique, indexed) | Telegram user id, recorded when first shared. |
| `display_name` | `str` (varchar(120)) | Customer's name as they gave it. |
| `created_at` | `datetime` (timestamptz) | First-seen timestamp. |
| `last_seen_at` | `datetime` (timestamptz) | Updated on every inbound message. |

**Validation**:
- `phone_e164` MUST match E.164 (`+\d{8,15}`); pydantic validator
  enforces.
- `display_name` length 1..120 after trim.

**Relationships**: 1..N `Address`, 1..N `ConfirmedOrder`.

**PII redaction**: `phone_e164`, `display_name` MUST go through
`redaction.redact(...)` before logging.

---

## Entity: Address

**Storage**: Postgres `addresses` table.

**Spec mapping**: Spec §Key Entities — saved addresses; FR-010, FR-013,
FR-015, FR-035.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` |  |
| `customer_id` | `UUID` (FK customers.id, indexed) |  |
| `kind` | `Literal["text", "location"]` (varchar(16)) | Discriminator. |
| `text_value` | `str | None` (text) | Free-form, present when `kind="text"` or location with a note. |
| `lat` | `float | None` (double precision) | Present when `kind="location"`. |
| `lon` | `float | None` (double precision) | Present when `kind="location"`. |
| `area_label` | `str | None` (varchar(80), indexed) | Normalized neighborhood/area name (e.g., "Hamra") used for in-zone matching. |
| `in_zone` | `bool` (boolean) | Computed at save time against `restaurant_info.json`'s `delivery.areas`. |
| `created_at` | `datetime` |  |

**Validation**:
- When `kind="text"`: `text_value` non-empty.
- When `kind="location"`: both `lat` and `lon` present; `text_value`
  optional landmark.
- `area_label` populated by `ZoneService.extract_area(...)` when a
  confident match exists; null when not confident (and `in_zone` is
  recorded as `True` in that case to honor the "not confident → don't
  warn" rule from R8).

**PII redaction**: `text_value`, `lat`, `lon` MUST be redacted.

---

## Entity: MenuItem

**Storage**: Postgres `menu_items` + `menu_chunks` (the latter for RAG).
Loaded from `data/menu_full_ar.json` at startup; the loader upserts into
Postgres so the dispatcher dashboard sees a consistent shape.

**Spec mapping**: Spec §Key Entities — Menu; FR-002, FR-005, FR-007.

`MenuItem`:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` (varchar(64)) | PK; stable id from the JSON corpus. |
| `category` | `str` (varchar(80)) | e.g., "mezze", "grills". |
| `name_en` | `str` |  |
| `name_ar` | `str` |  |
| `name_translit` | `str | None` | Optional Latin transliteration for matching. |
| `description_en` | `str | None` |  |
| `description_ar` | `str | None` |  |
| `price_usd` | `Decimal` (numeric(7,2)) | Base price in USD. |
| `available` | `bool` (boolean) | Honoured by FR-005. |
| `spice_level` | `Literal["none","mild","medium","spicy"] | None` |  |
| `tags` | `list[str]` (jsonb) | e.g., `["vegetarian","contains_dairy"]`. |

`MenuChunk` (for RAG):

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` |  |
| `menu_item_id` | `str` (FK menu_items.id) |  |
| `text` | `str` (text) | The chunk content (e.g., ingredients paragraph). |
| `language` | `Literal["en","ar"]` |  |
| `embedding` | `Vector(1024)` (pgvector) | `intfloat/multilingual-e5-large` output, computed locally via sentence-transformers. |

**Validation**: `price_usd` ≥ 0. `name_en` / `name_ar` non-empty.

---

## Entity: OrderDraft

**Storage**: Redis-only. Stored under key `draft:{customer_id}` as a JSON
blob with a 2-hour TTL. There is no Postgres mirror of in-flight drafts;
the first Postgres artifact in the order lifecycle is `ConfirmedOrder`
(see research.md R6).

**Spec mapping**: Spec §Key Entities — Order Draft; FR-003, FR-004,
FR-009, FR-016, FR-019, draft persistence assumption (2h).

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | New per draft. |
| `customer_id` | `UUID` (FK) |  |
| `items` | `list[OrderItem]` |  |
| `fulfillment` | `Literal["delivery","pickup"] | None` | None until chosen. |
| `address` | `Address | None` | Required when `fulfillment="delivery"` before confirm. |
| `language` | `Language` | Last detected language of the conversation. |
| `created_at` | `datetime` |  |
| `updated_at` | `datetime` |  |
| `expires_at` | `datetime` | `updated_at + 2h`. |

**Sub-entity OrderItem**:

| Field | Type | Notes |
|---|---|---|
| `menu_item_id` | `str` | FK to MenuItem.id; bot REFUSES to add an id absent from the menu (FR-005). |
| `quantity` | `int` | ≥ 1. |
| `customizations` | `list[Customization]` |  |

**Sub-entity Customization**:

| Field | Type | Notes |
|---|---|---|
| `kind` | `Literal["add","remove","cook_pref","extra_side","other"]` |  |
| `text` | `str` | Free-text annotation in the customer's language. |

**Validation rules** (enforced in `OrderService.validate_ready_to_confirm`):

- `len(items) >= 1` — else error code `EMPTY_CART`. FR-019.
- `fulfillment is not None` — else `MISSING_FULFILLMENT`. FR-019.
- `fulfillment == "delivery" implies address is not None` — else
  `MISSING_ADDRESS`. FR-019.
- Every `OrderItem.menu_item_id` resolves to an `available` MenuItem —
  else `ITEM_UNAVAILABLE`. FR-005.

---

## Entity: ConfirmedOrder

**Storage**: Postgres `orders` + `order_items` + `order_customizations`
tables. Immutable except for the dispatcher-facing fields below.

**Spec mapping**: Spec §Key Entities — Confirmed Order; FR-017, FR-020,
FR-021, FR-022, FR-023, FR-033, FR-035.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | Distinct from the draft id. |
| `customer_id` | `UUID` (FK) |  |
| `items_snapshot` | `list[OrderItem]` (jsonb) | Frozen at confirmation time so menu edits don't rewrite history. |
| `fulfillment` | `Literal["delivery","pickup"]` |  |
| `address_snapshot` | `Address | None` (jsonb) | Frozen copy. |
| `language` | `Language` | Conversation language for dispatcher follow-up (FR-033). |
| `transcript_url` | `str` | Link served by transcript_repo. |
| `estimated_total_usd` | `Decimal(7,2)` | Sum of `item.price_usd × quantity`. |
| `flags` | `list[Literal["out_of_zone_warning"]]` (jsonb) | FR-035. |
| `state` | `OrderState` (varchar(32)) | See state machine below. |
| `created_at` | `datetime` |  |
| `dispatcher_id` | `str | None` | Hash of token that last acted. |
| `dispatcher_actions` | relation → `DispatcherAction` |  |
| `entered_in_pos_at` | `datetime | None` |  |

### OrderState — state machine

```
awaiting_dispatcher_review
   │
   ├─── dispatcher edits ────►  awaiting_dispatcher_review   (idempotent)
   │
   ├─── mark_entered_in_pos ───►  entered_in_pos        (terminal-success)
   │
   └─── cancel (dispatcher) ───►  cancelled             (terminal-cancelled)
```

**Invariants** (Principle III; constitutional gate):

- `state` can only transition to `entered_in_pos` via
  `DispatcherService.mark_entered_in_pos(order_id, dispatcher_id)`.
  Asserted by an integration test that calls every other public mutation
  path and verifies `entered_in_pos_at` remains null.
- A confirmed order MUST NOT exist without an explicit customer Confirm
  callback having been recorded. Asserted by an integration test that
  fakes a webhook-internal-route bypass attempt and verifies it fails.

---

## Entity: DispatcherAction

**Storage**: Postgres `dispatcher_actions`. Append-only audit log.

**Spec mapping**: Spec §Key Entities — Dispatcher Action; FR-021, FR-022,
FR-025, FR-026.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` |  |
| `order_id` | `UUID | None` (FK orders.id) | Null for chat-only actions (escalations not tied to an order yet). |
| `conversation_id` | `UUID | None` (FK conversations.id) |  |
| `dispatcher_id` | `str` (varchar(64)) | Hash of bearer token used. |
| `dispatcher_name` | `str` (varchar(80), not null) | Self-reported operator name from the mutation request body. Trimmed, non-empty, ≤80 chars. Read-only endpoints do not write `DispatcherAction` rows, so this column is always populated. See research.md R12. |
| `action` | `Literal["review","edit","mark_entered_in_pos","cancel","take_over_chat","reply_in_chat","close_handoff"]` |  |
| `details` | `dict` (jsonb) | Action-specific payload. |
| `created_at` | `datetime` (indexed) |  |

---

## Entity: Conversation + Transcript

**Storage**: Postgres `conversations` (one row per chat session) +
`conversation_turns` (append-only message log).

**Spec mapping**: Spec §Key Entities — Conversation Transcript; FR-020
(transcript link), FR-024–FR-027 (escalation), FR-028–FR-032 (per-turn
language).

`Conversation`:

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` |  |
| `customer_id` | `UUID` (FK, indexed) |  |
| `started_at` | `datetime` |  |
| `last_activity_at` | `datetime` |  |
| `awaiting_human` | `bool` (boolean) | Set when escalated; cleared on `close_handoff`. |
| `assigned_dispatcher_id` | `str | None` | Token hash. |
| `active_draft_id` | `UUID | None` (uuid, no FK) | Mirror of the Redis `draft:{customer_id}` blob's `id`. Drafts live in Redis only; this column is informational and is cleared on confirmation or TTL expiry. |

`Turn`:

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` |  |
| `conversation_id` | `UUID` (FK, indexed) |  |
| `sender` | `Literal["customer","bot","dispatcher"]` |  |
| `text` | `str` (text) | Always redacted before logging; stored intact only inside the database, which is treated as a trust boundary. |
| `language` | `Language` | Detected per FR-028. |
| `intent` | `Intent | None` | From the classifier (FR-classifier-routing). |
| `created_at` | `datetime` |  |

---

## Entity: FailureCounter

**Storage**: Redis `failcount:{customer_id}:{field}` integer with TTL =
2h.

**Spec mapping**: FR-024 (3-strike escalation), Story 5.

| Key part | Meaning |
|---|---|
| `{customer_id}` | Customer's UUID. |
| `{field}` | One of: `order_parse`, `dish_match`, `address_extract`. |

Increment on each consecutive failure on the same field; reset when that
field resolves successfully or when escalation fires (so a dispatcher
takeover doesn't immediately re-escalate after takeover ends).

---

## Entity: ZoneEntry (in-zone area list)

**Storage**: Loaded from `data/restaurant_info.json` at startup;
materialized into Postgres `delivery_zones` (small table, ~30 rows) for
join queries from the dispatcher view.

**Spec mapping**: FR-035; Dependencies §1 of spec.

| Field | Type | Notes |
|---|---|---|
| `id` | `int` |  |
| `area_name` | `str` (varchar(80), unique) | e.g., "Hamra". |
| `aliases` | `list[str]` (jsonb) | e.g., `["حمرا","Hamrah"]`. |

Loader behavior (per R8): entries matching `^\[.*\]$` are stripped and a
single WARN log is emitted with the count of skipped placeholder rows.

---

## Cross-cutting: Language enum

```python
class Language(str, Enum):
    EN = "en"
    AR_LB = "ar_lb"
    ARABIZI = "arabizi"
```

Persisted as a varchar to keep migrations easy. `LanguageService.detect`
returns this; `LanguageService.reply_language(detected)` enforces
FR-031 (Arabizi input → English reply) at the service layer.

---

## Entity-to-FR traceability

| FR | Entity / field touched |
|---|---|
| FR-001 | MenuItem read (loader at startup) |
| FR-002 | MenuItem |
| FR-003 | OrderDraft.items |
| FR-004 | OrderItem.customizations |
| FR-005 | OrderDraft validate (MenuItem.available) |
| FR-006 | OrderItem.customizations — error path |
| FR-007 | MenuChunk + embedding |
| FR-008 | OrderDraft persists across turns |
| FR-009 | OrderDraft.fulfillment required pre-confirm |
| FR-010 | Address (kind=text or location) |
| FR-011 | Static reply; no entity |
| FR-012 | Customer.phone_e164 |
| FR-013 | Customer ←1..N Address (selection UI) |
| FR-014 | Customer create on confirm |
| FR-015 | Address create with FK to existing Customer |
| FR-016 | OrderDraft read-back |
| FR-017 | ConfirmedOrder created only via service |
| FR-018 | OrderDraft mutation preserves items |
| FR-019 | OrderDraft.validate_ready_to_confirm |
| FR-020 | ConfirmedOrder fields incl. `flags` |
| FR-021 | DispatcherAction("edit") |
| FR-022 | OrderState transition; entered_in_pos_at |
| FR-023 | OrderState invariant; integration test |
| FR-024 | FailureCounter increments |
| FR-025 | Conversation.awaiting_human + Turn history |
| FR-026 | Conversation.assigned_dispatcher_id; Turn(sender="dispatcher") |
| FR-027 | No "call us" turn template; lint check on prompt catalogue |
| FR-028 | Turn.language per turn |
| FR-029..FR-032 | LanguageService.reply_language |
| FR-033 | ConfirmedOrder.language |
| FR-034 | ExternalDependencyError → localized degradation Turn |
| FR-035 | Address.in_zone; ConfirmedOrder.flags |
