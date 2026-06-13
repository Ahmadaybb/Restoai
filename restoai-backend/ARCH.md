# Architecture: RestoAI Backend

## Layered architecture

The codebase follows strict Clean Architecture layering mandated by the
project constitution (Principle I). Import dependencies flow **inward only**
— outer layers may import inner layers but never the reverse.

```
┌─────────────────────────────────────────────────┐
│  app/api          (FastAPI routers, middleware)  │
│    telegram_router.py                            │
│    dispatcher/orders.py                          │
│    dispatcher/escalations.py                     │
│    dispatcher/auth.py                            │
│    health.py  ·  middleware.py                   │
├─────────────────────────────────────────────────┤
│  app/services     (business logic, orchestration)│
│    conversation_service.py                       │
│    order_draft_service.py  ·  order_service.py   │
│    customer_service.py  ·  escalation_service.py │
│    dispatcher_service.py  ·  language_service.py │
│    tools/  (parse_order, match_dish, …)          │
├─────────────────────────────────────────────────┤
│  app/repositories (SQL + Redis persistence)      │
│    customer_repo.py  ·  order_repo.py            │
│    transcript_repo.py  ·  menu_repo.py           │
├─────────────────────────────────────────────────┤
│  app/domain       (Pydantic models, Protocols)   │
│    customer.py  ·  order.py  ·  conversation.py  │
│    language.py  ·  tools.py  ·  errors.py        │
│    clients.py   (LLMClient, MessengerClient, …)  │
├──────────────────────┬──────────────────────────┤
│  app/infra           │  app/db                  │
│  (external adapters) │  (ORM models + engine)   │
│  groq_client.py      │  models.py               │
│  telegram_client.py  │  engine.py               │
│  embed_client.py     │                          │
│  redis_client.py     │                          │
│  draft_store.py      │                          │
│  settings.py         │                          │
│  redaction.py        │                          │
└──────────────────────┴──────────────────────────┘
```

**Enforcement**: `tests/architecture/test_layering.py` runs on every CI push
and asserts that no module in `app/repositories` imports from `app/services`
or `app/api`, and no module in `app/domain` imports from any other `app/`
layer. `tests/architecture/test_async_purity.py` asserts no `time.sleep` or
`requests` import appears in `app/api` or `app/services`.

---

## External integrations

| System | Adapter | Mode |
|--------|---------|------|
| Telegram Bot API | `app/infra/telegram_client.py` | Long-polling (dev) / webhook (prod) |
| Groq LLM API | `app/infra/groq_client.py` | Async — two tiers: mechanical (8B), synthesis (70B) |
| `intfloat/multilingual-e5-large` | `app/infra/embed_client.py` | CPU, `asyncio.to_thread` offload |
| PostgreSQL 16 + pgvector | `app/db/engine.py` + `app/repositories/` | asyncpg via SQLAlchemy async |
| Redis 7 | `app/infra/redis_client.py` + `app/infra/draft_store.py` | Conversation state (2h TTL), RQ queue |

All external adapters implement `app/domain/clients.py` Protocols. Tests stub
the protocols without importing any third-party SDK.

---

## Request lifecycle: Telegram inbound update

```
Telegram
  │
  ▼
POST /telegram/webhook/{secret_path}
  │
  ├─ RequestIdMiddleware sets request_id ContextVar
  │
  ▼
TelegramRouter.handle_update()  [background task]
  │
  ├─ Extract tg_user_id + chat_id from payload
  ├─ CustomerService.get_or_create_anonymous(tg_user_id)
  ├─ [T086] auto-set display_name from first_name if not yet set
  │
  ├─ /start ──► ConversationService.on_start()
  │               └─ send welcome + full menu
  │
  ├─ contact share ──► CustomerService.bind_phone_from_contact()
  │
  ├─ location share ──► OrderDraftService.attach_location()
  │
  ├─ callback_query ──► route by callback_data
  │     fulfillment:delivery/pickup  ──► OrderDraftService.set_fulfillment()
  │     confirm:<draft_id>           ──► OrderService.confirm()
  │     edit:<draft_id>              ──► OrderDraftService.reopen_for_edit()
  │     saved_address:<addr_id>      ──► OrderDraftService.select_saved_address()
  │     new_address                  ──► prompt for address text
  │
  └─ plain text ──► ConversationService.handle_text()
        │
        ├─ LanguageService.detect(text)
        ├─ TranscriptRepo.append_turn(inbound)
        ├─ [T095] if conv.awaiting_human → commit + return (no bot reply)
        ├─ IntentClassifier.classify(text)
        │
        ├─ Intent.ORDER ──► _handle_order_intent()
        │     ├─ parse_order tool  (mechanical LLM)
        │     ├─ match_dish tool   (mechanical LLM, per unresolved phrase)
        │     ├─ OrderDraftService.add_items()
        │     └─ render_readback tool  (synthesis LLM, when draft is ready)
        │
        ├─ Intent.QUERY ──► _handle_query_intent()
        │     └─ answer_menu_question tool
        │           ├─ EmbedderClient.embed(question)
        │           ├─ MenuRepo.vector_search()
        │           └─ synthesis LLM answer
        │
        └─ Intent.UNKNOWN ──► localized degradation message
              │
              └─ TelegramClient.send_message() ──► Telegram
```

---

## Request lifecycle: Dispatcher REST call

```
Dashboard / CLI
  │
  ▼
Authorization header: Bearer <DISPATCHER_API_TOKEN>
  │
  ├─ auth.require_auth()  → validates token, returns raw token string
  ├─ auth.validate_dispatcher_name()  → validates body.dispatcher_name
  │
  ├─ GET  /api/dispatcher/orders
  │     └─ DispatcherService.list_orders()  →  OrderRepo.list_awaiting_review()
  │
  ├─ PATCH /api/dispatcher/orders/{id}
  │     └─ DispatcherService.edit_order()
  │           ├─ OrderRepo.apply_edit()
  │           └─ OrderRepo.append_dispatcher_action(action="edit")
  │
  ├─ POST /api/dispatcher/orders/{id}/entered-in-pos
  │     └─ OrderService.mark_entered_in_pos(dispatcher_id, dispatcher_name)
  │           ├─ OrderRepo.set_state(entered_in_pos)
  │           └─ OrderRepo.append_dispatcher_action(action="entered_in_pos")
  │
  ├─ POST /api/dispatcher/orders/{id}/cancel
  │     └─ OrderService.cancel(dispatcher_id, dispatcher_name, reason)
  │
  ├─ GET  /api/dispatcher/escalations
  │     └─ DispatcherService.list_escalated()
  │           └─ TranscriptRepo.list_escalated()  (awaiting_human=True)
  │
  ├─ GET  /api/dispatcher/escalations/{id}
  │     └─ DispatcherService.get_escalation_detail()
  │           ├─ TranscriptRepo.get_turns()
  │           ├─ DraftStore.get_draft()  (Redis snapshot)
  │           └─ [optional] summarize_for_dispatcher tool  (synthesis LLM)
  │
  ├─ POST /api/dispatcher/escalations/{id}/take-over
  │     └─ EscalationService.take_over(dispatcher_id, dispatcher_name)
  │
  ├─ POST /api/dispatcher/escalations/{id}/messages
  │     └─ DispatcherService.send_message()
  │           ├─ TelegramClient.send_message("👤 [Support]: {text}")
  │           ├─ TranscriptRepo.append_turn(sender="dispatcher")
  │           └─ OrderRepo.append_dispatcher_action(action="reply_in_chat")
  │
  └─ POST /api/dispatcher/escalations/{id}/close-handoff
        └─ EscalationService.close_handoff()
              ├─ TranscriptRepo.update_conversation(awaiting_human=False)
              └─ DraftStore.reset_failcount()  (all three fields)
```

---

## Data flow: OrderDraft → ConfirmedOrder

```
Customer sends order text
  │
  ▼
ConversationService.handle_text()
  ├─ parse_order  ──►  OrderDraft.items updated in Redis
  ├─ match_dish   ──►  unresolved phrases resolved via menu index
  │
  ▼
Customer taps fulfillment button
  ├─ OrderDraftService.set_fulfillment("delivery"|"pickup")
  │
  ▼ (delivery only)
Customer shares address / location
  ├─ OrderDraftService.attach_address()  or  attach_location()
  │     └─ [T088] persists Address to Postgres when session provided
  │
  ▼
render_readback generates order summary + Confirm/Edit buttons
  │
  ▼
Customer taps ✅ Confirm
  │
  ▼
OrderService.confirm(session, customer, draft_id)
  ├─ validate_ready_to_confirm() — asserts items + fulfillment set
  ├─ check_zone()                — flags out-of-zone delivery addresses
  ├─ OrderRepo.create_confirmed()  ← first Postgres write in the order lifecycle
  ├─ CustomerService.persist_on_confirmation()  ← saves name + address (T089)
  ├─ DraftStore.delete_draft()   ← Redis draft removed
  └─ Conversation.active_draft_id updated
  │
  ▼
ConfirmedOrder in state: awaiting_dispatcher_review
  │
  ▼
Dispatcher calls POST /entered-in-pos
  ├─ OrderService.mark_entered_in_pos(dispatcher_id, dispatcher_name)
  └─ ConfirmedOrder.state → entered_in_pos  +  entered_in_pos_at set
```

---

## Data flow: Escalation

```
ConversationService (or OrderDraftService)
  ├─ parse_order failure  ──►  DraftStore.incr_failcount(customer_id, "order_parse")
  ├─ match_dish failure   ──►  DraftStore.incr_failcount(customer_id, "dish_match")
  └─ address_extract fail ──►  DraftStore.incr_failcount(customer_id, "address_extract")
                                        │
                              count reaches 3 on any field
                                        │
                                        ▼
                         EscalationService.register_failure()
                           ├─ Conversation.awaiting_human = True
                           ├─ DraftStore.reset_failcount(field)
                           └─ _try_enqueue_notify()  →  RQ: dispatcher_notify job
                                        │
                          Inbound customer messages
                           └─ ConversationService: turn recorded, NO bot reply
                                        │
                                        ▼
                         Dispatcher: GET /api/dispatcher/escalations
                           └─ sees conversation + transcript + DraftSummary
                                        │
                                        ▼
                         POST /escalations/{id}/take-over
                           └─ Conversation.assigned_dispatcher_id set
                                        │
                                        ▼
                         POST /escalations/{id}/messages
                           ├─ "👤 [Support]: {text}" sent via Telegram
                           └─ Turn(sender="dispatcher") persisted
                                        │
                                        ▼
                         POST /escalations/{id}/close-handoff
                           ├─ Conversation.awaiting_human = False
                           ├─ assigned_dispatcher_id cleared
                           └─ All failure counters reset
                                        │
                          Bot resumes normal replies
```

---

## Middleware chain

Every HTTP request passes through:

1. **RequestIdMiddleware** (`app/api/middleware.py`) — generates a UUID,
   sets it in a `ContextVar`, and adds it to every structured log record
   and every LLM cost-log entry. This is the correlation ID that ties a
   Telegram update to its LLM calls and any resulting database writes.

2. **FastAPI lifespan** (`app/main.py`) — at startup:
   - `Settings()` validated (hard boot failure on missing secrets)
   - Async DB engine and Redis pool opened
   - Intent classifier loaded from `data/intent_classifier.joblib`
   - `EmbedderClient` loaded (sentence-transformers, CPU)
   - `TelegramClient` started (polling or webhook)

---

## PII redaction

All free-form text that reaches a log writer or an LLM prompt passes through
`app/infra/redaction.py` — the single redaction utility. It scrubs Lebanese
phone formats (`+961…`, `03…`, `70…`), common Arabic names, and address
strings. No raw PII ever appears in a `structlog` record or a Groq prompt;
verified by `tests/infra/test_redaction.py`.
