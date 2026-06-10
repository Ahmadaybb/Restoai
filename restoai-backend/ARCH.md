# Architecture: RestoAI Backend

## Layered architecture overview

The codebase follows a strict Clean Architecture layering mandated by the
project constitution (Principle I). Import dependencies flow inward only:

```
app/api          →  app/services  →  app/repositories  →  app/db
                 →  app/domain
                 →  app/infra
```

| Layer | Purpose | May import from |
|-------|---------|-----------------|
| `app/api` | FastAPI routers, middleware, dependency factories | `services`, `domain`, `infra` |
| `app/services` | Business logic, orchestration, tool dispatch | `repositories`, `domain`, `infra` |
| `app/repositories` | SQL + Redis persistence | `domain`, `db`, `infra` |
| `app/domain` | Pydantic models, enums, error types, client Protocols | *(nothing internal)* |
| `app/infra` | External adapter implementations (Groq, Telegram, Redis, embedder) | `domain` |
| `app/db` | SQLAlchemy ORM models, async engine | *(nothing internal)* |
| `app/workers` | RQ background jobs | `services`, `domain`, `infra` |

Violations are caught at CI time by `tests/architecture/test_layering.py`.

## Request lifecycle

### Telegram inbound update

```
Telegram  →  POST /telegram/webhook/{secret_path}
          →  TelegramRouter.handle_update()
          →  ConversationService.handle_text()
          →  IntentClassifier.classify()
          →  Tool (parse_order / answer_menu_question / …)
          →  GroqClient / EmbedderClient  (if needed)
          →  OrderDraftService / OrderService  (if mutating state)
          →  TelegramClient.send_message()  →  Telegram
```

In development the bot uses long-polling instead of a webhook; the same
`handle_update` handler is called by the polling background task.

### Dispatcher REST call

```
Dashboard  →  POST /api/dispatcher/orders/{id}/entered-in-pos
           →  auth.py (bearer token check + dispatcher_name validation)
           →  DispatcherService.mark_entered_in_pos()
           →  OrderService.mark_entered_in_pos()
           →  OrderRepository (write ConfirmedOrder state + DispatcherAction row)
           →  200 OK
```

## External integrations

| System | Adapter | Notes |
|--------|---------|-------|
| Telegram Bot API | `app/infra/telegram_client.py` | Polling (dev) or webhook (prod) |
| Groq LLM API | `app/infra/groq_client.py` | Two tiers: mechanical, synthesis |
| sentence-transformers (local) | `app/infra/embed_client.py` | CPU; offloaded via `asyncio.to_thread` |
| PostgreSQL 16 + pgvector | `app/db/engine.py` + `app/repositories/` | asyncpg driver |
| Redis 7 | `app/infra/redis_client.py` + `app/infra/draft_store.py` | Conversation state, RQ queue |

## Data flow

### OrderDraft → ConfirmedOrder

```
Customer message
  → ConversationService creates / updates OrderDraft in Redis (2h TTL)
  → Customer presses Confirm inline button
  → ConversationService calls OrderService.confirm()
  → OrderService writes ConfirmedOrder + OrderItems to Postgres
  → OrderService deletes Redis draft
  → Dispatcher sees order in GET /api/dispatcher/orders
  → Dispatcher calls POST .../entered-in-pos
  → OrderService sets state=entered_in_pos + persists DispatcherAction
```

### Escalation flow

```
Three consecutive failures on the same field
  → EscalationService.register_failure() sets Conversation.awaiting_human=true
  → Summarize-for-dispatcher tool generates active_draft_summary
  → dispatcher_notify RQ job makes order visible in GET /api/dispatcher/escalations
  → Dispatcher takes over, messages customer via POST .../messages
  → TelegramClient forwards dispatcher text to customer, prefixed with attribution
  → Dispatcher calls POST .../close-handoff
  → EscalationService clears awaiting_human, resets counters
```
