---
description: "Dependency-ordered task list for feature 002-reservations"
---

# Tasks: Telegram Table Reservations

**Input**: Design documents from `/specs/002-reservations/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Tests are mandatory — the project constitution (Principle II) requires automated tests on critical paths and Pydantic schema validation.

**Organization**: Tasks are grouped by user story. Story 0 is shared foundation; US1–US4 are stacked in priority order (P1 first, then P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: Maps a task to its user story (US1–US4). Setup, Foundational, and Polish tasks have no story label.
- Every task includes a concrete file path and the FR(s) or research entry it implements.

---

## Phase 1: Setup — Story 0 (new entities + Alembic migration)

**Purpose**: Create the new domain models, ORM, migration, Redis draft store, and
repository that ALL user stories depend on. Nothing in US1–US4 can begin until
this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Create domain models in `app/domain/reservation.py`: `SeatingPreference` (StrEnum, 4 values), `ReservationState` (StrEnum: active/cancelled), `ReservationValidationCode` (StrEnum, 9 codes), `ReservationValidationError`, `ReservationDraft` (Pydantic, all fields nullable until collected), `Reservation` (Pydantic, all fields required, reference + state machine). Per data-model.md §SeatingPreference, §ReservationDraft, §Reservation, §ReservationValidationCode.

- [X] T002 [P] Add tool I/O schemas to `app/domain/tools.py`: `ExtractReservationFieldsIn` (text, language), `ExtractedReservationFields` (date|None, time|None, party_size|None, name|None, phone|None, date_is_informal: bool), `RenderReservationConfirmationIn` (reservation, language, is_modification: bool), `RenderReservationConfirmationOut` (text). Per `contracts/tool-schemas.md`.

- [X] T003 Add `Reservation` SQLAlchemy ORM class to `app/db/models.py` mirroring data-model.md §Alembic migration DDL: id (UUID PK), reference (varchar 12, unique), customer_id (FK), date, time, party_size (smallint), name (varchar 120), phone (varchar 20), seating_preference (varchar 24), state (varchar 16), language (varchar 16), created_at, updated_at, cancelled_at. Depends on T001.

- [X] T004 Create Alembic migration `alembic/versions/002_reservations_schema.py`: `CREATE TABLE reservations (...)` with all columns and indices from data-model.md §Alembic migration DDL (`ix_reservations_customer_id`, `ix_reservations_state`, `ix_reservations_reference`, `ix_reservations_date`). No changes to existing tables. Depends on T003.

- [X] T005 [P] Create Redis draft store `app/infra/reservation_draft_store.py` with `get_res_draft`, `put_res_draft`, `delete_res_draft` — key `res_draft:{customer_id}`, TTL = `DRAFT_TTL` (2h). Mirror the structure of `app/infra/draft_store.py`. Per research.md R10.

- [X] T006 Create reservation repository `app/repositories/reservation_repo.py` with async functions: `create(session, reservation) -> Reservation`, `get_by_id(session, reservation_id) -> Reservation | None`, `find_active_by_customer(session, customer_id) -> list[Reservation]`, `update(session, reservation_id, **fields) -> Reservation`, `cancel(session, reservation_id) -> Reservation`. SQL only — no HTTP errors raised. Depends on T001, T003.

- [X] T007 [P] Unit tests for domain model validation in `tests/domain/test_reservation.py`: parametrized test for every `ReservationValidationCode` path in `ReservationDraft` validation (missing_date, past_date, missing_time, missing_party_size, party_too_large, missing_name, missing_phone, missing_seating, terrace_too_large); enum exhaustiveness for `SeatingPreference`; Pydantic serialization round-trip for `Reservation`. Constitution Principle II.

**Checkpoint**: Foundation ready — domain, ORM, migration, draft store, and repository exist.

---

## Phase 2: Foundational (tools + service layer)

**Purpose**: LLM tools, prompt files, and services that all user stories share.
These have no story label; they are blocking prerequisites for US1–US4.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T008 [P] Create `app/prompts/en/extract_reservation_fields.txt`: mechanical-tier system prompt instructing the LLM to extract date, time, party_size, name, phone from free text; normalize informal dates to ISO-8601; set `date_is_informal: true` when the date was expressed informally; return strict JSON matching `ExtractedReservationFields`. Only extract reservation fields — ignore addresses, order items. Per research.md R11 and `contracts/tool-schemas.md`.

- [X] T009 [P] Create `app/prompts/ar_lb/extract_reservation_fields.txt`: Arabic (Lebanese dialect) equivalent of T008, accepting Arabic and Arabizi input.

- [X] T010 [P] Create `app/prompts/en/render_reservation_confirmation.txt`: synthesis-tier system prompt — waiter persona for Lakkis Farm; render a confirmation message that includes all FR-011 fields in natural language; use "updated" language when `is_modification=True`.

- [X] T011 [P] Create `app/prompts/ar_lb/render_reservation_confirmation.txt`: Arabic (Lebanese dialect) equivalent of T010.

- [X] T012 [P] Implement `app/services/tools/extract_reservation_fields.py`: async `extract_reservation_fields(inp: ExtractReservationFieldsIn, llm: LLMClient) -> ExtractedReservationFields`. Mechanical-tier LLM call; parse JSON response; on parse error return all-None result with `date_is_informal=False` rather than raise. Emit cost-log record. FR-002, FR-009. Per `contracts/tool-schemas.md` and research.md R11.

- [X] T013 [P] Implement `app/services/tools/render_reservation_confirmation.py`: async `render_reservation_confirmation(inp: RenderReservationConfirmationIn, llm: LLMClient) -> RenderReservationConfirmationOut`. Synthesis-tier LLM call; on LLM error fall back to a structured plain-text summary. Emit cost-log record. FR-011, FR-016. Per `contracts/tool-schemas.md`.

- [X] T014 [P] Unit test `tests/services/test_extract_reservation_fields.py`: mocked Groq — (a) valid extraction returns all fields; (b) informal date sets `date_is_informal=True`; (c) LLM JSON parse error returns all-None gracefully; (d) mechanical tier is called (synthesis MUST NOT be called — assert `complete_synthesis` never invoked). Principle II.

- [X] T015 [P] Unit test `tests/services/test_render_reservation_confirmation.py`: mocked synthesis LLM — (a) confirmation text contains reference number; (b) `is_modification=True` produces different prefix; (c) LLM failure falls back to plain-text summary without raising. Principle II.

- [X] T016 [P] Seating rules unit tests `tests/services/test_seating_rules.py`: (a) `OUTDOOR_TERRACE` with `party_size=5` → valid (no error); (b) `OUTDOOR_TERRACE` with `party_size=6` → raises `TERRACE_TOO_LARGE` (FR-006); (c) `party_size=14` → valid; (d) `party_size=15` → raises `PARTY_TOO_LARGE` (FR-007). Tests call `ReservationDraft.validate_ready_to_confirm()` or equivalent service method directly. Principle II.

- [X] T017 Implement `app/services/reservation_draft_service.py`: `start_draft(customer_id, language) -> ReservationDraft`; `get_draft(customer_id) -> ReservationDraft | None`; `delete_draft(customer_id)`; `collect_field(customer_id, field_name, value) -> ReservationDraft` (set one field, refresh TTL); `prefill_from_customer(customer_id, customer: Customer) -> ReservationDraft` (copy `display_name` → name, `phone_e164` → phone if set); `validate_ready_to_confirm(customer_id) -> ReservationDraft` (raise `ReservationValidationError` for any failing rule). FR-002, FR-009. Per research.md R13.

- [X] T018 [P] Unit test `tests/services/test_reservation_draft_service.py`: (a) `collect_field` updates correct field and refreshes TTL; (b) `prefill_from_customer` sets name + phone from `Customer`; (c) `validate_ready_to_confirm` raises correct `ReservationValidationCode` for each of the 9 failure modes (parametrized); (d) past date raises `PAST_DATE`; (e) valid draft returns the draft. Principle II.

**Checkpoint**: All tools and the draft service exist and are tested — user story implementation can now begin.

---

## Phase 3: User Story 1 — New customer places a reservation (Priority: P1) 🎯 MVP

**Goal**: A new customer completes a full table reservation end-to-end through the
Telegram bot, receiving an immediate confirmation message with a unique reference
number.

**Independent Test**: Per `quickstart.md §US1 — New customer places a reservation`.

- [ ] T019 [US1] Implement `ReservationService.confirm` in `app/services/reservation_service.py`: call `reservation_draft_service.validate_ready_to_confirm`; generate reference number `RES-` + 7 uppercase alphanumeric chars via `secrets.token_hex(4).upper()[:7]`; call `reservation_repo.create`; call `reservation_draft_service.delete_draft`; return the `Reservation` domain model. FR-010, FR-011, FR-012. Per research.md R3, R6.

- [ ] T020 [P] [US1] Unit test for `ReservationService.confirm` in `tests/services/test_reservation_service.py`: (a) produces a `Reservation` with reference matching `^RES-[A-Z0-9]{7}$`; (b) deletes the draft on success; (c) raises `ReservationValidationError` when draft fails validation; (d) repository `create` is called exactly once. Principle II.

- [ ] T021 [US1] Add `Intent.RESERVATION` branch in `app/services/conversation_service.py` `handle_text`: route to `_handle_reservation_intent(session, customer, text, reply_lang, llm, conv.id)`. The existing `ORDER` / `QUERY` branches are untouched. FR-001. Per plan.md §modified files.

- [ ] T022 [US1] Implement `_handle_reservation_intent` in `app/services/conversation_service.py`: (1) read `chat_state.waiting_for` from `draft_store.get_chat_state`; (2) if no active state, call `extract_reservation_fields` to pre-fill any fields provided upfront and `prefill_from_customer`; (3) dispatch to field-collection sub-handlers based on `waiting_for`; (4) when draft passes `validate_ready_to_confirm`, call `ReservationService.confirm` and send the confirmation message. FR-001, FR-002, FR-009. Per research.md R13.

- [ ] T023 [US1] Terrace hard-block in the seating dialog within `_handle_reservation_intent`: when a customer selects `outdoor→terrace` and `draft.party_size > 5`, explain the 5-person terrace maximum, offer **Outdoor (non-terrace)** and **Indoor** as alternatives via inline buttons, and set `waiting_for = "reservation_seating_reask"` rather than confirming. FR-006. Per plan.md §Summary.

- [ ] T024 [US1] Add reservation callback handlers to `app/api/telegram_router.py`: parse `res_seating:*` (indoor, outdoor, indoor_smoking, indoor_non_smoking, outdoor_terrace, outdoor_non_terrace) calling `reservation_draft_service.collect_field`; parse `res_date_confirm:{customer_id}:{iso_date}` saving the confirmed date; parse `res_date_retry` resetting `waiting_for` to `"reservation_date"`. Per `contracts/telegram-callbacks.md`.

- [ ] T025 [US1] Add localized field prompts (EN + AR_LB) as constants or a prompt catalogue in `app/services/conversation_service.py` (or `app/services/reservation_prompts.py`): one prompt string per collection step — date, time, party_size, name, phone, indoor/outdoor choice, smoking/non-smoking choice, terrace choice, date read-back confirmation. FR-002, FR-003, FR-004, FR-005, FR-020–FR-024.

- [ ] T026 [US1] Date read-back confirmation flow in `_handle_reservation_intent`: when `extract_reservation_fields` returns `date_is_informal=True`, send the normalized date in `DD Month YYYY` format (e.g., "20 June 2026") with `res_date_confirm:` / `res_date_retry` inline buttons, and set `waiting_for = "reservation_date_confirm"`. Resume normal collection on confirm; re-ask date on retry. FR-009.

- [ ] T027 [US1] E2E test `tests/e2e/test_us1_reservation_happy_path.py`: mock Groq + Redis + Postgres; drive the full flow (RESERVATION intent → extract fields → seating dialog → confirm); assert (a) `Reservation` domain object has all FR-011 fields; (b) reference matches `^RES-[A-Z0-9]{7}$`; (c) confirmation message text is sent to Telegram messenger; (d) draft is deleted after confirmation. Principle II.

**Checkpoint**: US1 complete — a new customer can book a table end-to-end.

---

## Phase 4: User Story 2 — Party too large: redirect to call center (Priority: P1)

**Goal**: When party size is stated as more than 14, the bot immediately redirects
to call center 1661 and collects no further reservation fields.

**Independent Test**: Per `quickstart.md §US2 — Party too large: redirect to call center`.

- [ ] T028 [US2] Party-too-large guard in `app/services/reservation_draft_service.py` `collect_field`: add the `party_size > 14` check as the FIRST validation when `field_name == "party_size"`; raise `ReservationValidationError(PARTY_TOO_LARGE)` immediately so the caller can emit the redirect message before writing the draft. FR-007. This is the earliest possible check — no other collection step may precede it.

- [ ] T029 [US2] Load call center phone from `data/restaurant_info.json` in `app/repositories/zone_repo.py` (or a dedicated `get_call_center_phone() -> str` function in `app/infra/restaurant_info.py`): read `restaurant.contact.phone`; LRU-cache at startup; never hardcode `"1661"` in service or routing code. Per research.md R5, ADR-014.

- [ ] T030 [P] [US2] Localized call center redirect messages (EN + AR_LB) in `app/services/conversation_service.py`: when `_handle_reservation_intent` catches `PARTY_TOO_LARGE`, reply with a message that quotes the call center number from T029. FR-007.

- [ ] T031 [P] [US2] Unit test (extend `tests/services/test_reservation_draft_service.py`): `collect_field("party_size", 15)` raises `PARTY_TOO_LARGE` before any other field is written or any LLM call is made; `collect_field("party_size", 14)` succeeds. FR-007. Principle II.

**Checkpoint**: US1 + US2 complete — both P1 stories are green.

---

## Phase 5: User Story 3 — Customer modifies a reservation (Priority: P2)

**Goal**: A customer can change date, time, party size, or seating on an active
reservation. Party size change that invalidates terrace triggers seating re-ask.
Multiple active reservations are presented as an inline button list.

**Independent Test**: Per `quickstart.md §US4 — Modification`.

- [ ] T032 [US3] Implement `ReservationService.modify` in `app/services/reservation_service.py`: accept `reservation_id`, `customer_id`, and a `fields: dict` of the fields to update; call `reservation_repo.update`; preserve the `reference` column unchanged; return the updated `Reservation`. FR-013, FR-014, FR-016. Per research.md R6.

- [ ] T033 [US3] Terrace re-ask on party size conflict in `app/services/reservation_service.py` `modify` (or in `_handle_modification_intent`): after updating `party_size`, check if `seating_preference == OUTDOOR_TERRACE` and `new_party_size > 5`; if so, do NOT persist the change immediately — instead return a `ReservationValidationError(TERRACE_TOO_LARGE)` so the caller can trigger the seating re-ask. FR-015.

- [ ] T034 [US3] Direct seating change flow in `_handle_modification_intent` in `app/services/conversation_service.py`: when `chat_state.waiting_for == "reservation_modify_seating"`, drive the full seating selection dialog (indoor/outdoor → sub-choice), then call `ReservationService.modify(seating_preference=...)` and send re-confirmation. FR-016b.

- [ ] T035 [US3] Multi-reservation inline button list: in `_handle_modification_intent`, call `reservation_repo.find_active_by_customer`; if result count > 1, build `res_select:{reservation_id}` inline buttons with label `{reference} — {day} {date} {time}`, set `waiting_for = "reservation_select_for_modify"`, and return the selection prompt. R9. Per `contracts/telegram-callbacks.md §Multi-reservation selection`.

- [ ] T036 [US3] Add `res_select:` callback handler in `app/api/telegram_router.py`: parse `reservation_id` from the callback data, load from Redis `chat_state` which action (modify or cancel) was pending, then proceed to the appropriate handler. Per `contracts/telegram-callbacks.md`.

- [ ] T037 [US3] Add modification intent routing in `_handle_reservation_intent` in `app/services/conversation_service.py`: detect modification keywords ("change", "update", "modify", "بدّل", "غيّر") via `chat_state.waiting_for` or as a new classifier label; call `reservation_repo.find_active_by_customer`; if exactly one result, proceed to `_handle_modification_intent`; if more than one, invoke the multi-reservation button list (T035). FR-013, FR-014.

- [ ] T038 [P] [US3] Unit tests in `tests/services/test_reservation_service.py` (extend): (a) `modify` updates date correctly, reference unchanged; (b) `modify` with `party_size=6` on a terrace booking raises `TERRACE_TOO_LARGE` (FR-015); (c) `modify` with `party_size=4` on a terrace booking succeeds; (d) `modify` seating directly from terrace to indoor_non_smoking succeeds. Principle II.

**Checkpoint**: US1 + US2 + US3 complete — both P1 and the first P2 story are green.

---

## Phase 6: User Story 4 — Customer cancels a reservation (Priority: P2)

**Goal**: A customer can cancel an active reservation with an explicit Yes/No
confirmation gate. Cancellation is acknowledged with the reference number.

**Independent Test**: Per `quickstart.md §US5 — Cancellation`.

- [ ] T039 [US4] Implement `ReservationService.cancel` in `app/services/reservation_service.py`: set `state = "cancelled"`, set `cancelled_at = now()`, call `reservation_repo.cancel(session, reservation_id)`. FR-019. Per data-model.md §ReservationState.

- [ ] T040 [US4] Cancellation intent routing in `_handle_reservation_intent` in `app/services/conversation_service.py`: detect cancellation keywords ("cancel", "إلغاء"); call `reservation_repo.find_active_by_customer`; if none found, reply "no active reservation"; if one, send summary + `res_cancel_confirm:{id}` / `res_cancel_abort:{id}` inline buttons; if multiple, invoke multi-reservation button list with `waiting_for = "reservation_select_for_cancel"`. FR-017, FR-018. Per `contracts/telegram-callbacks.md §Cancellation confirmation`.

- [ ] T041 [US4] Add `res_cancel_confirm:` and `res_cancel_abort:` callback handlers in `app/api/telegram_router.py`: on confirm, call `ReservationService.cancel` and send localized acknowledgement with reference number; on abort, send "your reservation is still active" message. FR-017, FR-018, FR-019. Per `contracts/telegram-callbacks.md`.

- [ ] T042 [P] [US4] Unit tests in `tests/services/test_reservation_service.py` (extend): (a) `cancel` sets state to `"cancelled"` and `cancelled_at` is not None; (b) calling cancel on an already-cancelled reservation is a no-op (state stays `"cancelled"`). Principle II.

- [ ] T043 [P] [US4] Unit test: cancellation when `find_active_by_customer` returns empty list → reply text contains "no active reservation" (EN) and does NOT call `cancel`. FR-017. Principle II.

**Checkpoint**: All four user stories complete — US1, US2, US3, US4 are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, PII redaction assertions, architecture gate validation,
and cost-log verification.

- [ ] T044 [P] Append ADR-011 through ADR-014 to `DECISIONS.md` (immediate confirmation HITL deviation, Redis-only draft, SeatingPreference enum, call-center-number-as-config). Constitution Principle VI. Per plan.md §Architecture decisions to record.

- [ ] T045 [P] Add PII redaction assertions to `tests/infra/test_redaction.py`: prove that `redact(name)` scrubs a sample customer name appearing in a reservation context; prove that `redact(phone)` scrubs a Lebanese E.164 phone. Constitution Principle V.

- [ ] T046 [P] Verify architecture layering for new files: extend `tests/architecture/test_layering.py` to assert that `app/api/telegram_router.py` (reservation callbacks) imports only from `app/services` and `app/domain` — not from `app/repositories` or `app/db`. Constitution Principle I.

- [ ] T047 [P] Cost-log smoke test: in `tests/services/test_extract_reservation_fields.py` (extend) and `tests/services/test_render_reservation_confirmation.py` (extend), assert that each tool call triggers exactly one `cost_log.record(...)` call (mock `cost_log` and assert it is called with `model`, `input_tokens`, `output_tokens`, `est_cost_usd`). Constitution Principle IV.

- [ ] T048 Run `ruff check . && mypy app/domain app/services app/api app/infra` against all new files and fix any violations. Constitution Principle I.

- [ ] T049 [P] Run the full test suite `pytest tests/ -v` and confirm all tests pass (target: 0 failures, ≤ 1 skip for live-DB RAG retrieval). Constitution Principle II.

- [ ] T050 Quickstart validation: bring up `docker compose up --build`, run through `quickstart.md §US1` through `§US5` manually, confirm all five scenarios pass against the running stack. Principle III — end-to-end human validation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Story 0)**: No dependencies — start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. Blocks all user stories.
- **Phase 3 (US1)**: Depends on Phase 2. This is the MVP; validate independently before moving on.
- **Phase 4 (US2)**: Depends on Phase 2. Can start in parallel with Phase 3.
- **Phase 5 (US3)**: Depends on Phases 3 and 4 (modification reuses confirm and relies on reservation existing).
- **Phase 6 (US4)**: Depends on Phase 3 (cancel needs a confirmed reservation).
- **Phase 7 (Polish)**: Depends on all prior phases being complete.

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2, US3, or US4.
- **US2 (P1)**: Can start after Phase 2 — single guard check, independent of US1 implementation.
- **US3 (P2)**: Depends on US1 (`Reservation` must exist to modify) and the repository from Phase 1.
- **US4 (P2)**: Depends on US1 (`Reservation` must exist to cancel).

### Within Each User Story

- Domain/service tasks before router/handler tasks.
- Tests may be written first (TDD) or alongside implementation — both are valid.
- Core feature before edge cases (e.g., T019 confirm before T026 date read-back).

### Parallel Opportunities

- T001, T002, T005, T007 (Phase 1) can all run in parallel.
- T008–T016, T018 (Phase 2 prompts + tool tests) can all run in parallel.
- T017 (ReservationDraftService) must precede T019 (ReservationService.confirm).
- T020, T027 (US1 tests) can run in parallel with T021–T026 (US1 implementation).
- T028–T031 (US2) can run concurrently with T019–T027 (US1) once Phase 2 is done.

---

## Parallel Example: Phase 2

```text
# All prompt files in parallel (T008–T011):
Task T008: app/prompts/en/extract_reservation_fields.txt
Task T009: app/prompts/ar_lb/extract_reservation_fields.txt
Task T010: app/prompts/en/render_reservation_confirmation.txt
Task T011: app/prompts/ar_lb/render_reservation_confirmation.txt

# Tools and their tests in parallel (T012–T015):
Task T012: extract_reservation_fields tool
Task T013: render_reservation_confirmation tool
Task T014: unit test for extract_reservation_fields
Task T015: unit test for render_reservation_confirmation
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1 (Story 0 foundation).
2. Complete Phase 2 (Foundational tools + service layer).
3. Complete Phase 3 (US1 — happy path booking).
4. Complete Phase 4 (US2 — call center redirect).
5. **STOP and VALIDATE**: run `quickstart.md §US1` and `§US2` against docker compose.
6. Demo and ship MVP.

### Incremental Delivery

1. Phases 1–2 → Foundation ready.
2. Phase 3 → US1 live, independently testable.
3. Phase 4 → US2 live alongside US1.
4. Phase 5 → US3 (modification) added.
5. Phase 6 → US4 (cancellation) added.
6. Phase 7 → Polish, docs, and gate validation.

---

## Notes

- **[P]** tasks touch different files — safe to run in parallel.
- **[Story]** label maps each task to its user story for traceability.
- `app/infra/reservation_draft_store.py` must use key prefix `res_draft:` to avoid collision with order drafts (`draft:`). Research.md R10.
- The `>14` guard (T028) is the FIRST check in `collect_field` — no draft is written, no LLM is called, no seating dialog starts for oversized parties.
- The call center number is read from `data/restaurant_info.json` at startup (T029) — never hardcoded. ADR-014.
- No dispatcher dashboard tasks in this spec — that is a separate future feature.
