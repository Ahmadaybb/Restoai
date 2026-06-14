# Feature Specification: Telegram Table Reservations

**Feature Branch**: `002-reservations`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Table reservations via Telegram for Lakkis Farm restaurant. Customers can reserve a table, receive immediate confirmation with a reference number, and later cancel or modify their reservation. Seating rules: indoor (smoking/non-smoking) or outdoor (terrace max 5 people). Party > 14 → call center at 1661. Multilingual: EN/AR/Arabizi."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — New customer places a table reservation end-to-end (Priority: P1)

A customer opens a chat with the bot and asks to reserve a table. The bot
collects the required details: date, time, party size, name, and phone number.
It then asks the customer whether they prefer indoor or outdoor seating. For
indoor, it asks smoking or non-smoking area. For outdoor, it asks whether they
want the terrace (subject to the 5-person maximum). Once all details are
collected, the bot confirms the reservation immediately and sends a message
containing all booking details and a reference number — with no human approval
step in between.

**Why this priority**: This is the MVP. Without this story nothing else
matters. Every other story is an enhancement of this happy path.

**Independent Test**: A tester who has never interacted with the bot opens
Telegram, starts a reservation request, provides all required fields (date,
time, party size ≤ 14, name, phone), selects a seating preference, and
receives a confirmation message that includes a unique reference number,
date, time, party size, name, phone, and seating details. No other feature
is required for this test to pass.

**Acceptance Scenarios**:

1. **Given** a customer types any reservation intent ("I want to book a
   table", "احجز طاولة"), **When** the bot detects the intent, **Then** the
   bot begins collecting the required details in the conversation language.
2. **Given** the bot has started collecting reservation details, **When**
   the customer provides date, time, party size, name, and phone number,
   **Then** the bot stores each field and proceeds to the seating step
   without repeating fields already provided.
3. **Given** all required fields are collected, **When** the bot asks
   "indoor or outdoor?", **Then** for indoor the bot asks smoking or
   non-smoking; for outdoor the bot asks if the customer wants the terrace.
4. **Given** the customer chooses the terrace and party size ≤ 5, **When**
   the bot has all details, **Then** it confirms immediately with a message
   containing: reference number, date, time, party size, name, phone, and
   seating (terrace).
5. **Given** all required fields are collected and seating is chosen,
   **When** the bot confirms the reservation, **Then** the confirmation
   message contains every required field and a unique reference number.

---

### User Story 2 — Party too large for the bot: redirect to call center (Priority: P1)

A customer tries to reserve for a group larger than 14 people. The bot cannot
accept the reservation and must direct the customer to the call center at 1661
without collecting any other reservation details.

**Why this priority**: A group > 14 should never be allowed through the
bot — the call center needs to handle special arrangements. Silently collecting
their details and then rejecting at the end would be poor UX. The check must
happen as soon as party size is known.

**Independent Test**: A tester sends a reservation request stating 15 (or
more) guests. The bot must reply with a message that explains the bot cannot
handle groups of that size and directs the customer to call 1661. No other
fields (date, time, name, phone, seating) should be requested.

**Acceptance Scenarios**:

1. **Given** a customer provides a party size greater than 14 at any point
   in the collection flow, **When** the bot detects this, **Then** the bot
   stops the reservation flow, explains that groups over 14 must call the
   call center, and provides the number 1661.
2. **Given** the bot has redirected to the call center, **When** the
   customer asks to continue with the reservation in the same chat, **Then**
   the bot repeats the redirect message and does not collect further details.

---

### User Story 3 — Customer modifies an existing reservation (Priority: P2)

A customer who has an active reservation wants to change the date, time, or
party size. They send a message referencing their reservation (or the bot
looks it up by their phone number), and the bot lets them pick which field
to change. After the change, the bot re-confirms with updated details. If the
new party size affects seating validity (e.g., the original booking was for
the terrace and the new party size is 6), the bot re-asks the seating
preference.

**Why this priority**: Reservations frequently change. Without modification
support, the customer would have to cancel and re-book, doubling the
interaction cost. P2 because the product is usable without it (US1 ships a
complete booking flow on its own).

**Independent Test**: From a completed US1 reservation, a tester sends a
modification request (e.g., "change the time to 8 PM"). The bot identifies
the reservation by phone number, applies the change, and resends a
confirmation message with the updated details and the same reference number.
Then the tester modifies the party size from 3 to 6 on a terrace booking —
the bot must detect the terrace conflict and ask the customer to reselect
their seating preference.

**Acceptance Scenarios**:

1. **Given** a customer with an active reservation sends a modification
   intent ("I want to change my booking"), **When** the bot identifies the
   reservation by their phone number, **Then** the bot presents the current
   booking and asks which field to change (date, time, or party size).
2. **Given** the customer selects a field to change, **When** they provide
   the new value, **Then** the bot updates the field, re-confirms the full
   reservation, and retains the same reference number.
3. **Given** the customer changes their party size and the new size exceeds
   the terrace maximum (5 people) while the current seating is terrace,
   **When** the bot detects the conflict, **Then** it explains the terrace
   limitation and asks the customer to reselect their seating preference
   (outdoor non-terrace or indoor).
4. **Given** the customer reselects a valid seating option after a terrace
   conflict, **When** the bot receives the choice, **Then** it updates the
   seating on the reservation and re-confirms all details.

---

### User Story 4 — Customer cancels a reservation (Priority: P2)

A customer who has an active reservation wants to cancel it. They send a
cancellation intent ("cancel my reservation") and the bot locates their
reservation by phone number, shows the booking details, and asks for
confirmation. On confirmation, the bot cancels the reservation and acknowledges
the cancellation.

**Why this priority**: Cancellations are a basic hygiene feature. Without
them, customers who can't make it have no way to free the table. P2 because
US1 and US3 already form a usable reservation system without cancellation.

**Independent Test**: From a completed US1 reservation, a tester sends "cancel
my booking". The bot must display the reservation details, ask "Are you sure?",
and on confirmation reply with a cancellation acknowledgement that includes
the reference number.

**Acceptance Scenarios**:

1. **Given** a customer sends a cancellation intent, **When** the bot
   identifies their reservation by phone number, **Then** it shows the
   current booking details and asks the customer to confirm the cancellation.
2. **Given** the bot has asked for cancellation confirmation, **When** the
   customer confirms, **Then** the bot marks the reservation as cancelled and
   sends an acknowledgement containing the reference number.
3. **Given** the bot has asked for cancellation confirmation, **When** the
   customer replies "no" or does not confirm, **Then** the bot keeps the
   reservation active and returns to the normal conversation state.
4. **Given** a customer sends a cancellation intent but has no active
   reservation, **When** the bot searches by phone number and finds nothing,
   **Then** the bot informs the customer that no active reservation was found.

---

### Edge Cases

- **Terrace request with party size exactly 5**: permitted — bot confirms
  terrace seating without conflict.
- **Terrace request with party size 6 or more**: bot must explain the
  terrace limit and offer alternatives (outdoor non-terrace or indoor) before
  any confirmation.
- **Party size stated as more than 14**: bot must immediately redirect to
  call center 1661 and collect no further fields.
- **Customer provides date in the past**: bot must reject the date and ask
  for a future date.
- **Customer modifies a cancelled reservation**: bot informs that the
  reservation is no longer active and offers to start a new booking.
- **Customer has multiple active reservations**: bot lists them all (with
  reference numbers) and asks which one to modify or cancel.
- **Customer switches language mid-reservation flow**: each message is
  detected independently; the reply language follows the input language per
  the Language Handling rules — the collected data fields are language-agnostic.
- **Phone number not shared**: if the customer's Telegram profile has no
  phone number and no prior phone number is stored, the bot requests it via
  Telegram contact-share or free-text entry.
- **Bot or LLM fails mid-flow**: the customer receives a clear localized
  error message and is invited to retry or restart the reservation — never
  a stack trace or silent failure.
- **Customer sends a date in non-standard format** (e.g., "next Friday",
  "17/6"): the bot interprets the date and reads it back for the customer
  to confirm before proceeding.

## Requirements *(mandatory)*

### Functional Requirements

**Reservation intake (covers US1, US2)**

- **FR-001**: System MUST detect a reservation intent from any natural-language
  message in English, Arabic (Lebanese dialect), or Arabizi and begin the
  reservation collection flow.
- **FR-002**: System MUST collect the following fields before confirming a
  reservation: date, time, party size, customer name, and phone number.
- **FR-003**: System MUST ask whether the customer prefers indoor or outdoor
  seating after all other required fields are collected.
- **FR-004**: When the customer selects indoor, system MUST ask whether they
  want the smoking or non-smoking area.
- **FR-005**: When the customer selects outdoor, system MUST ask whether they
  want the terrace.
- **FR-006**: System MUST reject a terrace request when the party size is
  greater than 5, explain the terrace maximum, and offer outdoor non-terrace
  or indoor as alternatives. The reservation MUST NOT be confirmed with
  terrace seating for a party larger than 5.
- **FR-007**: System MUST detect when party size is greater than 14 at the
  earliest opportunity (when party size is first stated), immediately stop
  the reservation flow, and direct the customer to call the call center at
  1661. System MUST NOT collect any further reservation fields in this case.
- **FR-008**: System MUST reject a date that is in the past and ask for a
  future date.
- **FR-009**: When the customer provides a date in an informal format (e.g.,
  "next Friday"), system MUST parse it, read it back in an unambiguous format
  (day and date), and ask for confirmation before proceeding.

**Confirmation (covers US1)**

- **FR-010**: System MUST confirm a reservation immediately upon collecting
  all required fields and a valid seating choice, with no human approval step.
- **FR-011**: The confirmation message MUST contain: reference number, date,
  time, party size, customer name, phone number, and seating preference
  (including smoking/non-smoking for indoor or terrace/non-terrace for outdoor).
- **FR-012**: System MUST generate a unique reference number for each
  confirmed reservation. The same reference number MUST be used if the
  reservation is subsequently modified.

**Modification (covers US3)**

- **FR-013**: System MUST allow a customer to modify the date, time, party
  size, or seating preference of an active reservation by referencing their
  booking in conversation.
- **FR-014**: System MUST identify the customer's reservation by their phone
  number when they request a modification.
- **FR-015**: When the modified party size causes the existing terrace seating
  to become invalid (new size > 5), system MUST inform the customer of the
  conflict and re-ask the seating preference before re-confirming.
- **FR-016**: After a successful modification, system MUST re-confirm all
  updated details with the original reference number.
- **FR-016b**: When the customer requests to change seating preference
  directly, system MUST walk them through the seating selection flow again
  (indoor → smoking/non-smoking, or outdoor → terrace check) and re-confirm
  with updated seating details and the original reference number. If the new
  seating is terrace and party size > 5, system MUST apply FR-006 (terrace
  block) before confirming.

**Cancellation (covers US4)**

- **FR-017**: System MUST allow a customer to cancel an active reservation
  in the same Telegram conversation.
- **FR-018**: Before cancelling, system MUST show the current booking details
  and request explicit confirmation from the customer.
- **FR-019**: Upon confirmed cancellation, system MUST acknowledge the
  cancellation with the reference number and mark the reservation as cancelled.

**Language handling (cross-cutting)**

- **FR-020**: System MUST detect the language of every incoming customer
  message independently of prior messages in the conversation.
- **FR-021**: System MUST reply in English when the incoming message is in
  English.
- **FR-022**: System MUST reply in Arabic (Lebanese dialect) when the incoming
  message is in Arabic (Lebanese dialect).
- **FR-023**: System MUST fully understand Arabizi (Lebanese Arabic written in
  Latin letters) on input but MUST reply in English when the incoming message
  is in Arabizi.
- **FR-024**: System MUST adapt the reply language on the next turn when the
  customer switches input language mid-conversation.
- **FR-025**: System MUST persist the language(s) of the conversation on the
  reservation record.

**Graceful degradation (cross-cutting)**

- **FR-026**: When any tool, model, or external dependency fails, system MUST
  present the customer with a clear, localized error message and an explicit
  next step (retry or restart) — never a stack trace, untranslated string, or
  silent failure.

### Key Entities

- **Reservation**: a confirmed table booking. Has a unique reference number,
  customer name, customer phone number, date, time, party size, seating
  preference (indoor-smoking, indoor-non-smoking, outdoor-terrace,
  outdoor-non-terrace), state (active, cancelled), and the language(s) of the
  conversation. Belongs to a Customer.
- **ReservationDraft**: the in-progress data collection state before
  confirmation. Holds all partially-collected fields, validates them
  progressively, and is discarded when the reservation is confirmed or the
  customer abandons the flow. Belongs to a Customer.
- **Customer**: identified by their Telegram phone number (shared as a
  contact or previously stored). Has a name and zero or more past
  reservations.
- **SeatingPreference**: a typed value representing the seating choice:
  indoor-smoking, indoor-non-smoking, outdoor-terrace, or outdoor-non-terrace.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new customer can complete a full reservation (all fields
  collected, seating chosen, confirmation received) in under 3 minutes, with
  no human intervention, in at least 80% of attempted sessions.
- **SC-002**: Customers who request more than 14 people are redirected to the
  call center without any other fields being collected in 100% of cases — zero
  partial-collection sessions for oversized groups reach confirmation.
- **SC-003**: Terrace bookings for groups larger than 5 are blocked in 100%
  of cases — zero confirmed reservations with terrace seating for party
  size > 5.
- **SC-004**: Confirmed reservations contain every required field (reference
  number, date, time, party size, name, phone, seating) in at least 98% of
  cases, with no missing or blank fields reaching the customer confirmation
  message.
- **SC-005**: Customer messages in Arabic (Lebanese dialect) receive Arabic
  replies; messages in English receive English replies; messages in Arabizi
  receive English replies the customer can understand. Measured on a held-out
  evaluation set, language-routing accuracy is ≥ 95%.
- **SC-006**: A customer with an active reservation can cancel it successfully
  in under 90 seconds of interaction, measured from cancellation intent to
  acknowledgement.
- **SC-007**: Reservation modification (single field change) completes
  successfully in under 2 minutes in at least 80% of attempted sessions.

## Assumptions

- **Channel**: Telegram is the only customer-facing channel for this feature.
  WhatsApp and other channels are out of scope.
- **No availability check**: The bot enforces only two hard rules: terrace
  maximum of 5 people, and the > 14 call-center redirect. General table
  availability is out of scope — the restaurant manages capacity independently.
- **No dispatcher review**: Reservations are confirmed immediately without
  a human approval step, unlike orders in the takeaway feature. The
  restaurant is comfortable with bot-confirmed bookings.
- **Single active reservation per phone number**: A customer is assumed to
  have at most one active reservation at a time. Multiple concurrent active
  reservations are not supported in v1; if the customer books again, the
  previous reservation remains active and the new one is added alongside it
  (bot will list both for modification/cancellation requests).
- **Operating hours**: The bot does not check whether the requested date/time
  falls within restaurant opening hours in v1. The restaurant reviews all
  bookings manually and contacts customers if there is an issue.
- **Reference number format**: A short alphanumeric code (e.g., RES-4F2A)
  is sufficient. No globally unique guarantee beyond reasonable collision
  resistance is required for v1.
- **Phone number source**: Customer phone is collected via Telegram contact
  share or free-text if not already stored from a prior order (feature 001)
  or reservation.
- **Modifications**: Date, time, party size, and seating preference may be
  modified via the bot. Name and phone number cannot be modified via bot in
  v1 — the customer must cancel and re-book to change these fields.
- **Payments and deposits**: No payment is collected for reservations.
  Out of scope entirely.
- **Multilingual scope**: Arabizi is supported for input only. Generating
  Arabizi reliably is out of scope (same constraint as feature 001).
- **Identity**: Customer identity is the Telegram phone number. Customers
  who refuse to share their phone cannot complete a reservation in v1.

## Dependencies

- A Telegram bot identity and webhook endpoint authorized to receive customer
  messages and inline-button callbacks (shared with the takeaway ordering
  feature, feature 001).
- Customer profile store (phone number, name) from feature 001 — a returning
  customer who has previously ordered will have their name and phone pre-filled.
- A persisted reservation store (reference number, all reservation fields,
  state) accessible within the same conversation and across sessions.
- A configured call center phone number (1661) surfaced to the bot as
  configuration, not hardcoded.
