# Telegram Webhook Contract

**Feature**: `001-takeaway-orders`

This document specifies the contract for the inbound Telegram surface.
There is exactly one HTTP endpoint plus one polling loop (only one is
active in a given environment).

## Endpoint

`POST /telegram/webhook/{secret_path}`

- `{secret_path}` is a random URL segment configured via
  `TELEGRAM_WEBHOOK_SECRET_PATH`. Compared in constant time.
- A separate `X-Telegram-Bot-Api-Secret-Token` header MUST equal
  `TELEGRAM_WEBHOOK_SECRET`. Mismatch returns 401 without logging the
  body.
- Body: a Telegram `Update` JSON, parsed by python-telegram-bot's
  decoder.

The handler returns `200 OK` with an empty body once the update has been
enqueued for processing. Processing is non-blocking; reply messages are
sent back via the Bot API as separate calls.

## Polling mode (dev)

If `TELEGRAM_WEBHOOK_URL` is empty in `Settings`, the FastAPI lifespan
handler starts a single background coroutine running
`Application.run_polling(allowed_updates=[...])`. No public URL needed.

Exactly one mode is active per process. The selection happens once at
boot and never flips at runtime.

## Update types consumed

| Telegram type | Where it goes |
|---|---|
| `message.text` | `ConversationService.handle_text(customer, text, lang_hint=None)`. |
| `message.contact` | `CustomerService.bind_phone(customer, contact.phone_number)`. |
| `message.location` | `OrderDraftService.attach_location(customer, lat, lon)`. |
| `callback_query` (data `"confirm:{draft_id}"`) | `OrderService.confirm(customer, draft_id)`. |
| `callback_query` (data `"edit:{draft_id}"`) | `OrderDraftService.reopen_for_edit(customer, draft_id)`. |
| `callback_query` (data `"saved_address:{address_id}"`) | `OrderDraftService.select_saved_address(customer, address_id)`. |
| Anything else | Ignored with a debug log. |

Spec requirement coverage: FR-001 (welcome on `/start`), FR-009..FR-011
(fulfillment via inline keyboard), FR-013 (saved address callback),
FR-016..FR-018 (Confirm/Edit callbacks), FR-026 (incoming text routed to
dispatcher when `Conversation.awaiting_human=true`).

## Inline keyboards

| Keyboard | Buttons | Triggered by |
|---|---|---|
| **fulfillment** | `🛵 Delivery` / `🏪 Pickup` | After items are parsed and customer has not yet chosen. FR-009. |
| **saved_addresses** | One button per saved address + `🆕 New address` | When a returning customer chooses delivery. FR-013. |
| **confirm** | `✅ Confirm` / `✏️ Edit` | At read-back. FR-016. |

Localized labels per language; the bot sends the keyboard in the same
language as the last detected input.

## Outbound delivery

All outbound messages go through `TelegramClient.send_message(...)` which:

- Applies the response language per `LanguageService.reply_language(...)`.
- Passes the prompt-rendered text through a final-stage sanitizer that
  guarantees no untranslated string template placeholders leak.
- Records latency and message size in the structured log (`request_id`
  correlation preserved across the entire turn).

## Failure handling

If sending fails (network, rate limit, Telegram 5xx), the call is
enqueued on RQ with exponential backoff up to 5 minutes. After three
failed attempts the conversation is flagged
`Conversation.awaiting_human=true` and surfaced in the dispatcher's
escalation queue per FR-026/FR-034.
