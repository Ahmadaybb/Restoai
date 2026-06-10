# Feature Specification: Telegram Takeaway Ordering with Dispatcher Review

**Feature Branch**: `001-takeaway-orders`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Spec the takeaway ordering flow for RestoAI — a Telegram-based ordering bot for a Lebanese restaurant. Customers chat with the bot, build an order (delivery or pickup), confirm it, and the structured order arrives in a dispatcher dashboard where a human reviews it and enters it into the Omega POS manually. AI is never a direct write-path to the POS. Bot must work in English, Arabic (Lebanese dialect), and Arabizi (input only)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — New customer places a complete order end-to-end (Priority: P1)

A first-time customer opens a chat with the bot, is greeted, sees the menu, types
their order in natural language ("2 hummus, 1 fattoush, 1 grilled chicken"),
specifies delivery or pickup (providing an address if delivery), reviews a read-back
of the order with the estimated total, presses **Confirm**, and the structured
order arrives in the dispatcher dashboard where a human operator reviews it and
marks it as entered in the POS.

**Why this priority**: This is the MVP. Without it, no order ever reaches the
restaurant. Every other story below is an enhancement of this happy path.

**Independent Test**: A tester who has never interacted with the bot opens
Telegram, starts the chat, completes a delivery order (giving phone, name,
address), confirms it, and verifies the order appears in the dispatcher
dashboard with all required fields. Repeat for a pickup order (no address). No
other features are required for this test to pass.

**Acceptance Scenarios**:

1. **Given** a brand-new customer with no profile, **When** they open the chat
   with the bot, **Then** they receive a welcome message and the menu (organized
   by category with items underneath) before being asked anything.
2. **Given** the customer is shown the menu, **When** they type a direct order
   like "2 hummus, 1 fattoush, 1 grilled chicken", **Then** the bot parses the
   items, confirms what it understood, and asks for any missing information
   (delivery vs pickup, address if delivery, contact name and phone if not
   already known).
3. **Given** the customer chose delivery, **When** they provide a delivery
   address, **Then** the bot stores it on the order in the language and form the
   customer used.
4. **Given** the customer chose pickup, **When** they confirm pickup, **Then**
   the bot tells them the pickup location.
5. **Given** the order has at least one item and a fulfillment choice (and an
   address for delivery), **When** the bot reads the full order back (items,
   quantities, delivery/pickup, address if delivery, estimated total) and
   presents inline **Confirm** / **Edit** buttons, **Then** the customer can
   confirm or return to editing without losing items already added.
6. **Given** the customer presses **Confirm**, **When** the bot forwards the
   order to the dispatcher dashboard, **Then** the order appears in the
   dispatcher queue with: customer name, phone, address (or "pickup"), every
   item with quantity, language of the conversation, link to the chat
   transcript, and estimated total.
7. **Given** the dispatcher reviews the order in the dashboard, **When** they
   click **Entered in POS** after manually entering it in Omega POS, **Then**
   the order moves out of the "awaiting POS entry" state.

---

### User Story 2 — Customer asks menu questions while ordering (Priority: P2)

A customer wants to know about a dish before committing: ingredients, spice
level, portion size, price. They ask in natural language ("is the kibbeh spicy?",
"what's in the fattoush?", "how big is the mixed grill?"). The bot answers from
the menu corpus and the conversation continues seamlessly into building the
order — questions and ordering happen in the same chat, not in separate flows.

**Why this priority**: A significant share of customers will not know the menu
by heart. Without Q&A they fall back to direct ordering only (US1), which still
works — so this is P2, not P1. But it materially expands who can order without
a human.

**Independent Test**: Starting from a working US1 flow, a tester asks 3–5 menu
questions of different types (ingredient, price, spice, portion) in a single
conversation, then completes an order. Each answer must come from the menu
corpus, not be hallucinated, and the order built afterwards must complete and
land in the dispatcher dashboard exactly as in US1.

**Acceptance Scenarios**:

1. **Given** the bot has presented the menu, **When** the customer asks "what's
   in the fattoush?", **Then** the bot answers from the menu corpus with the
   listed ingredients.
2. **Given** a customer asks about a dish that exists on the menu, **When** the
   bot responds, **Then** the response is grounded in the menu corpus and the
   bot does not invent ingredients, prices, or spice information.
3. **Given** a customer asks about a dish that does not exist on the menu,
   **When** the bot responds, **Then** the bot says so plainly and offers the
   closest available items rather than fabricating one.
4. **Given** the customer has asked menu questions, **When** they pivot to
   ordering ("ok, then I'll take 2 fattoush"), **Then** the bot adds the items
   to the same order draft and continues from US1's flow without restarting.

---

### User Story 3 — Customer adds customizations to items (Priority: P2)

A customer adds modifiers to any item: "extra hummus on the side", "no onions
in the fattoush", "well-done", "with extra bread", "spicy". The bot captures
each customization alongside its parent item in the structured order so the
dispatcher and the kitchen see exactly what the customer asked for.

**Why this priority**: A real restaurant order frequently includes
customizations. The product is usable without them (a customer could just type
plain orders), but it would feel rigid. P2 because US1 ships a complete order
flow on its own.

**Independent Test**: From a working US1 flow, a tester places an order
containing at least three different customizations across different items
(quantity modifier, ingredient remove, cooking preference). Each customization
must appear, attached to the correct item, in both the customer's read-back and
the dispatcher's view.

**Acceptance Scenarios**:

1. **Given** a customer has added an item, **When** they ask for "extra hummus
   on the side" or "no onions", **Then** the bot captures the customization on
   that item in the order draft.
2. **Given** the customer has added customizations, **When** the bot reads the
   order back for confirmation, **Then** each customization appears under its
   parent item in the read-back.
3. **Given** the order arrives at the dispatcher, **When** the dispatcher views
   the order, **Then** each item is displayed with its quantity and all of its
   customizations in plain language.
4. **Given** the bot does not understand a requested customization, **When** it
   cannot map it confidently, **Then** the bot asks the customer to clarify
   rather than silently dropping it.

---

### User Story 4 — Returning customer recognized and offered saved address (Priority: P3)

A customer who has ordered before opens a new chat. The bot recognizes them by
their Telegram-shared phone number, greets them by name, and — if they're
ordering for delivery — offers their saved address(es) as a one-tap choice
("Welcome back Maya! Deliver to your usual address on Hamra Street?"). New
customers continue with the standard collection flow from US1.

**Why this priority**: A delight feature that meaningfully reduces friction for
the restaurant's repeat customers, but the product works without it (everyone
just enters details every time). P3.

**Independent Test**: Place a first order as a new customer (saving phone,
name, address). End the chat. Reopen the chat. The bot must greet by name and
offer the saved address. Choose the saved address with one tap and complete a
new order without re-typing personal details.

**Acceptance Scenarios**:

1. **Given** a customer has placed at least one prior order, **When** they
   start a new chat, **Then** the bot looks them up by the Telegram phone
   number they have shared and greets them by name if found.
2. **Given** a returning customer is recognized and is placing a delivery
   order, **When** the bot asks for delivery details, **Then** the bot offers
   their saved address(es) as inline options the customer can pick with one
   tap.
3. **Given** a returning customer wants to deliver somewhere new, **When** they
   choose "use a different address", **Then** they can enter a fresh address
   that gets saved alongside the existing ones.
4. **Given** a new customer is placing their first order, **When** they reach
   the personal-details collection step, **Then** the bot collects phone (via
   Telegram contact share or typed), name, and (for delivery) address, and
   saves them on order confirmation for future recognition.

---

### User Story 5 — Bot can't understand → escalate to human handler in-channel (Priority: P3)

When the bot fails to make progress on the same point three times in a row
(can't parse the order, can't match a dish, can't extract a usable address), it
escalates the chat to a human handler in the dispatcher dashboard. The human
takes over the conversation in the same Telegram chat with the full transcript
visible. The bot never loops indefinitely and never tells the customer to
"call a phone number" — escalation stays in-channel.

**Why this priority**: A safety net for edge cases that protects trust. The
product can ship without it (most customers will succeed via US1), but it
should land before public launch. P3 — must exist, not blocking MVP demo.

**Independent Test**: A tester sends three consecutive messages on the same
field that the bot cannot resolve (e.g., a deliberately garbled address). On
the third failure, the chat must appear in the dispatcher's "needs human"
queue with the full transcript; a dispatcher then replies in the dashboard and
the customer receives that reply in the same Telegram chat.

**Acceptance Scenarios**:

1. **Given** the bot is trying to resolve a field (order items, address, dish
   match), **When** it fails to make progress three consecutive turns on that
   same field, **Then** it stops trying autonomously and posts the chat to the
   dispatcher's "needs human" queue.
2. **Given** a chat has been escalated, **When** the dispatcher opens it,
   **Then** the dispatcher sees the full conversation transcript and the
   current order draft (if any).
3. **Given** the dispatcher replies in the dashboard, **When** they send a
   message, **Then** the customer receives that message in the same Telegram
   chat, attributed clearly as coming from a human operator.
4. **Given** a chat is in human-handled state, **When** the customer sends
   further messages, **Then** they go to the dispatcher (not the bot) until
   the dispatcher closes the human-handoff.

---

### Edge Cases

- **Out-of-stock or unavailable item**: customer orders an item that the menu
  marks unavailable. The bot must say it's unavailable and offer alternatives,
  not silently drop it from the order or pretend to add it.
- **Order with zero items at confirmation time**: customer presses Confirm
  before adding anything. The bot must refuse and prompt for at least one item.
- **Customer abandons mid-order**: customer disappears after adding items but
  before confirming. The draft persists per the Assumptions section; on the
  customer's next message the bot offers to resume or start over.
- **Customer switches language mid-conversation**: each incoming message is
  detected independently, and the reply language follows the input language per
  the Language Handling rules below.
- **Mixed-language single message** (e.g., "بدي 2 hummus please"): the bot must
  understand the order and respond in the dominant language of that message;
  edge-case behaviour does not block confirmation.
- **Customer presses Edit after read-back**: the bot returns to the order-
  building state with the existing items, customizations, and fulfillment
  choice preserved — nothing is wiped.
- **Customer sends a Telegram Location instead of typing an address**: bot
  accepts and stores the coordinates plus any landmark text the customer adds.
- **Out-of-zone delivery address**: customer provides a delivery address
  outside the restaurant's configured delivery zones. The bot warns the
  customer and flags the order; the dispatcher decides whether to accept it.
- **Same customer opens a second chat while one is mid-flight**: the active
  draft is shared by customer identity (Telegram phone), so the bot continues
  the existing draft rather than starting a new one.
- **Bot is down or an underlying tool fails**: the customer sees a clear,
  localized message and is offered the option to wait or to be escalated to a
  human handler — never a stack trace, never silent failure.

## Requirements *(mandatory)*

### Functional Requirements

**Welcome and menu (covers US1, US2)**

- **FR-001**: System MUST send a welcome message and present the full menu
  (categories with items underneath) automatically when a customer starts a
  new chat with the bot, before any other interaction.
- **FR-002**: System MUST present the menu in a form that fits the chat
  interface (readable on Telegram without external attachments being required).

**Direct order parsing and item handling (covers US1, US3)**

- **FR-003**: System MUST parse free-text orders of the form "N item, N item,
  …" into a structured order draft of items with quantities.
- **FR-004**: System MUST attach customer-requested customizations
  (modifiers, removals, cooking preferences, extras) to the specific item
  they apply to in the order draft.
- **FR-005**: System MUST refuse to add an item that does not exist on the
  current menu and instead offer the closest available alternatives.
- **FR-006**: System MUST refuse to silently drop a customization it cannot
  map; it MUST ask the customer to clarify it instead.

**Menu Q&A in conversation (covers US2)**

- **FR-007**: System MUST answer menu-related questions (ingredients, spice
  level, portion size, price) grounded in the menu corpus; it MUST NOT
  fabricate menu information.
- **FR-008**: System MUST allow menu Q&A and order building to occur in the
  same conversation, preserving the order draft across question turns.

**Fulfillment choice and address handling (covers US1, US4)**

- **FR-009**: System MUST require the customer to choose delivery or pickup
  before allowing the order to reach confirmation.
- **FR-010**: System MUST collect a delivery address when the customer chooses
  delivery; the address MAY be free-form text, a Telegram Location, or both.
- **FR-011**: System MUST communicate the pickup location to the customer when
  the customer chooses pickup.
- **FR-035**: System MUST check delivery addresses against a configured list
  of in-zone areas. When an address appears out-of-zone, the system MUST warn
  the customer in their language, flag the order with `out-of-zone-warning`
  for the dispatcher, and continue the flow without blocking confirmation.

**Customer recognition and profile (covers US4)**

- **FR-012**: System MUST identify returning customers by the phone number
  they share through Telegram and greet them by their stored name.
- **FR-013**: System MUST offer a recognized returning customer their saved
  delivery address(es) as inline one-tap options when they choose delivery.
- **FR-014**: System MUST collect phone, name, and (for delivery) address from
  new customers during the order flow and persist them on confirmation for
  future recognition.
- **FR-015**: System MUST allow a recognized customer to choose a new address
  for the current order; the new address MUST be saved alongside existing
  addresses.

**Confirmation gate (covers US1)**

- **FR-016**: System MUST read the full order back to the customer (items with
  quantities and customizations, fulfillment choice, address if delivery,
  estimated total) and present inline **Confirm** and **Edit** buttons before
  the order leaves the chat.
- **FR-017**: System MUST NOT forward an order to the dispatcher until the
  customer has pressed **Confirm**.
- **FR-018**: System MUST preserve all items, customizations, fulfillment
  choice, and address when the customer presses **Edit**, returning them to
  the order-building state without data loss.
- **FR-019**: System MUST block confirmation if the order has zero items, no
  fulfillment choice, or (when delivery) no address.

**Dispatcher dashboard (covers US1, US5)**

- **FR-020**: System MUST deliver every confirmed order to the dispatcher
  dashboard with: customer name, customer phone, delivery address (or the
  literal "pickup"), every item with its quantity and its customizations, the
  language the conversation was conducted in, a link to the chat transcript,
  the estimated total, and any flags set on the order (including
  `out-of-zone-warning` when applicable).
- **FR-021**: System MUST allow the dispatcher to edit a confirmed order in
  the dashboard before marking it as entered in the POS.
- **FR-022**: System MUST allow the dispatcher to mark an order as "Entered in
  POS" with a single click, after which the order moves out of the awaiting-
  entry queue.
- **FR-023**: System MUST NOT have any path that sends an order to the POS or
  any other restaurant fulfillment system without both (a) the customer
  pressing **Confirm** in chat and (b) the dispatcher marking it entered in
  the dashboard.

**Human-in-the-loop escalation (covers US5)**

- **FR-024**: System MUST count consecutive failures on the same field (order
  parse, dish match, address extraction) and, after three such consecutive
  failures, escalate the chat to a human handler in the dispatcher dashboard.
- **FR-025**: System MUST present the escalated chat to the dispatcher with
  the full conversation transcript and the order draft in its current state.
- **FR-026**: System MUST route messages between the customer's Telegram chat
  and the dispatcher dashboard in both directions while the chat is in
  human-handled state, identifying dispatcher messages as coming from a human
  operator.
- **FR-027**: System MUST NOT tell the customer to call a phone number, leave
  the channel, or otherwise abandon the conversation as a failure mode.

**Language handling (cross-cutting; covers all user stories)**

- **FR-028**: System MUST detect the language of every incoming customer
  message independently of prior messages in the conversation.
- **FR-029**: System MUST reply in English when the incoming message is in
  English.
- **FR-030**: System MUST reply in Arabic (Lebanese dialect) when the incoming
  message is in Arabic (Lebanese dialect).
- **FR-031**: System MUST fully understand Arabizi (Lebanese Arabic written in
  Latin letters) on input but MUST reply in English when the incoming message
  is in Arabizi.
- **FR-032**: System MUST adapt the reply language on the next turn when the
  customer switches input language mid-conversation.
- **FR-033**: System MUST persist on the order the language(s) of the
  conversation so the dispatcher knows what to expect on follow-up contact.

**Graceful degradation (cross-cutting)**

- **FR-034**: When any tool, model, or external dependency fails, the system
  MUST present the customer with a clear, localized error message and an
  explicit next step (retry, abandon, or escalate to a human handler) — never
  a stack trace, untranslated string, or silent failure.

### Key Entities

- **Customer**: a person who chats with the bot. Identified by their Telegram
  phone number. Has a name and zero or more saved delivery addresses.
- **Menu**: the source of truth for items the customer can order. Each menu
  item has a category, a name (in each supported language), an availability
  flag, a price, and descriptive metadata (ingredients, portion size, spice
  level) used to answer Q&A.
- **Order Draft**: the in-progress order during a chat. Holds items with
  quantities and customizations, fulfillment choice (delivery or pickup), an
  address if delivery, and the running estimated total. Belongs to a Customer.
- **Confirmed Order**: an Order Draft that the customer pressed **Confirm**
  on. In addition to draft fields, it has the language(s) of the conversation,
  a link to the chat transcript, and a dispatcher-facing lifecycle state
  (awaiting review → reviewed → entered in POS).
- **Dispatcher Action**: an audit record of what a human operator did to an
  order (review, edit, mark entered in POS, takeover-handoff in/out).
- **Conversation Transcript**: the full message history of a chat, kept for
  the dispatcher's reference and for escalations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new customer can complete a full delivery order from welcome to
  dispatcher hand-off in under 5 minutes, with no human intervention, in at
  least 80% of attempted sessions.
- **SC-002**: For confirmed orders that reach the dispatcher, at least 95%
  contain every required field (customer name, phone, address or "pickup",
  every item with quantity, customizations, language, transcript link,
  estimated total) without dispatcher correction.
- **SC-003**: A dispatcher can review and mark a confirmed order as entered in
  the POS in under 60 seconds of dashboard interaction for a typical order
  (≤5 items, ≤3 customizations).
- **SC-004**: A returning customer who has previously saved an address is
  greeted by name and offered a one-tap saved address at least 95% of the
  time, measured across the first 100 returning-customer sessions.
- **SC-005**: Customer messages in Arabic (Lebanese dialect) receive Arabic
  replies; messages in English receive English replies; messages in Arabizi
  receive English replies the customer can understand. Measured on a held-out
  evaluation set, language-routing accuracy is ≥95%.
- **SC-006**: When the bot cannot make progress on the same field three times
  in a row, the chat is escalated to a dispatcher with the full transcript in
  100% of cases — there are no infinite-loop sessions in production logs.
- **SC-007**: Zero orders reach the POS without both customer confirmation and
  dispatcher confirmation. Measured continuously via audit log; any occurrence
  is a sev-1 incident.
- **SC-008**: Order accuracy (the dispatcher's view of the order matches what
  the customer intended) is at least 95%, measured by dispatcher-reported
  edits required at review time. Order accuracy is the headline quality
  metric, privileged over latency per the project constitution.

## Assumptions

- **Channel**: Telegram is the only customer-facing channel for v1. WhatsApp
  and other channels are explicitly out of scope.
- **POS write-path**: The dispatcher enters orders into Omega POS manually via
  a human-driven workflow. There is no machine-to-machine integration with the
  POS in v1.
- **Pricing model**: Menu item prices come from the menu corpus (each item
  has a base price in USD). The estimated total shown to the customer is the
  sum of `item.price × quantity`. Customizations are recorded as free-text
  annotations on items in v1 — they are NOT separately priced. The
  customer-facing read-back shows the estimated total based on item prices
  only, with a note that "final pricing is confirmed by the dispatcher when
  entering the order in the POS." Pricing customizations is explicitly
  deferred to a future version.
- **Delivery zones**: The bot validates delivery addresses against a
  configured list of in-zone neighborhoods/areas (provided by the restaurant
  in `restaurant_info.json`). When the customer provides a delivery address,
  the bot extracts the neighborhood/area name and checks it against the zone
  list. If the address appears to be out-of-zone, the bot warns the customer
  ("We don't usually deliver to that area — let me check with our team") and
  routes the order to the dispatcher with an `out-of-zone-warning` flag for
  manual review. The bot does NOT block the order; the dispatcher makes the
  final call and contacts the customer if needed.
- **Address shape**: Delivery addresses are stored as free-form text and/or
  Telegram Location coordinates. A normalized street/building schema is not
  required for v1 because Lebanese addressing is conventionally landmark-
  based.
- **Draft persistence**: An unfinished order draft persists for 2 hours after
  the customer's last message. On the customer's next message within that
  window, the bot offers to resume or start over. Beyond 2 hours, the draft
  is discarded and a new conversation starts fresh.
- **Menu source**: The menu corpus is maintained by a separate workflow and is
  loaded by this system. Changes to menu sourcing and editing are out of
  scope for this spec.
- **Identity**: Customer identity is the Telegram phone number the customer
  shares. Customers who refuse to share their phone cannot complete an order
  in v1, because the dispatcher needs a callback number.
- **Transcript link**: The dispatcher dashboard receives a link to the full
  chat transcript. The transcript store and its retention policy are owned by
  an adjacent spec and assumed to exist.
- **Payments**: No payments are handled by this system. Payment is taken
  in-person at delivery or pickup.
- **Multilingual scope for v1**: Arabizi is supported for input only.
  Generating Arabizi reliably is out of scope because it lacks standard
  orthography.
- **Single restaurant**: This spec covers a single restaurant brand. Multi-
  tenant operation is out of scope.

## Dependencies

- A maintained menu corpus (items, categories, prices, descriptions, spice
  levels, availability) in all supported display languages.
- A dispatcher dashboard surface where operators can: view the queue, review
  and edit confirmed orders, mark orders as "Entered in POS", view the "needs
  human" queue, take over an escalated chat, and send messages back to the
  customer's Telegram chat.
- A persisted conversation transcript store reachable via a link from the
  dashboard.
- A Telegram bot identity and webhook endpoint authorized to receive customer
  messages and inline-button callbacks.
- A configured list of in-zone delivery neighborhoods/areas, maintained in
  `restaurant_info.json` alongside the menu corpus.
