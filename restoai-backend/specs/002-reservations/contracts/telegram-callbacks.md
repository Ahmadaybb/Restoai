# Contract: Telegram Callback Data — Reservations

**Feature**: `002-reservations` | **Date**: 2026-06-13

Inline button `callback_data` values emitted by the reservation flow.
These strings are parsed by `app/api/telegram_router.py` in the
`CallbackQueryHandler`.

---

## Seating selection

| Button label (EN) | `callback_data` |
|---|---|
| 🪑 Indoor | `res_seating:indoor` |
| 🌿 Outdoor | `res_seating:outdoor` |
| 🚬 Smoking | `res_seating:indoor_smoking` |
| 🚭 Non-Smoking | `res_seating:indoor_non_smoking` |
| 🏡 Terrace | `res_seating:outdoor_terrace` |
| 🌳 Outdoor (non-terrace) | `res_seating:outdoor_non_terrace` |

**Parser rule**: `callback_data.startswith("res_seating:")`

---

## Cancellation confirmation

| Button label (EN) | `callback_data` |
|---|---|
| ✅ Yes, cancel | `res_cancel_confirm:{reservation_id}` |
| ❌ No, keep it | `res_cancel_abort:{reservation_id}` |

`{reservation_id}` is the Postgres UUID of the `Reservation` row (not
the human-readable reference). This keeps the callback routable without
an extra DB lookup by reference.

**Parser rules**:
- `callback_data.startswith("res_cancel_confirm:")`
- `callback_data.startswith("res_cancel_abort:")`

---

## Multi-reservation selection (modify/cancel)

When the customer has more than one active reservation:

| Button label | `callback_data` |
|---|---|
| `RES-4F2A7B3 — Fri 20 Jun 8 PM` | `res_select:{reservation_id}` |

`{reservation_id}` is the Postgres UUID.

**Parser rule**: `callback_data.startswith("res_select:")`

The `intent_action` (modify vs cancel) is read from
`chat_state:{customer_id}.waiting_for` which is set before the selection
buttons are presented.

---

## Date confirmation (informal date read-back)

When the bot parses an informal date and reads it back for confirmation:

| Button label | `callback_data` |
|---|---|
| ✅ Yes, that's correct | `res_date_confirm:{customer_id}:{iso_date}` |
| ✏️ No, let me re-type | `res_date_retry` |

`{iso_date}` is the ISO-8601 date string (`YYYY-MM-DD`).

**Parser rules**:
- `callback_data.startswith("res_date_confirm:")`
- `callback_data == "res_date_retry"`
