# Contract: Tool Input/Output Schemas — Reservations

**Feature**: `002-reservations` | **Date**: 2026-06-13

Pydantic models for the reservation LLM tool. These live in
`app/domain/tools.py` alongside the existing order tool schemas.

---

## Tool: extract_reservation_fields

**File**: `app/services/tools/extract_reservation_fields.py`
**LLM tier**: Mechanical (cheap model)
**Spec mapping**: FR-002, FR-009, research.md R11

### Input

```python
class ExtractReservationFieldsIn(BaseModel):
    text: str               # raw customer message (≤ 1000 chars)
    language: Language      # detected conversation language
```

### Output

```python
class ExtractedReservationFields(BaseModel):
    date: date | None       # ISO-8601; None if not stated
    time: time | None       # ISO-8601 24h; None if not stated
    party_size: int | None  # None if not stated; may be > 14
    name: str | None        # customer name; None if not stated
    phone: str | None       # raw phone string; None if not stated
    date_is_informal: bool  # True when the date was phrased informally
                            # (e.g. "next Friday") and must be read back
                            # for customer confirmation before saving
```

**System prompt location**: `app/prompts/en/extract_reservation_fields.txt`
and `app/prompts/ar_lb/extract_reservation_fields.txt`

---

## Tool: render_reservation_confirmation

**File**: `app/services/tools/render_reservation_confirmation.py`
**LLM tier**: Synthesis (stronger model)
**Spec mapping**: FR-011, FR-016

### Input

```python
class RenderReservationConfirmationIn(BaseModel):
    reservation: Reservation   # domain model (or ReservationDraft at preview)
    language: Language
    is_modification: bool = False  # True → "updated" language in message
```

### Output

```python
class RenderReservationConfirmationOut(BaseModel):
    text: str   # Localized confirmation message ready to send
```

The confirmation message MUST include: reference number, date, time,
party size, name, phone, and seating preference in localized form.
No buttons are attached (confirmation is text-only).

---

## Domain errors

```python
class ReservationValidationError(Exception):
    def __init__(self, code: ReservationValidationCode, detail: str = "") -> None:
        ...

class ReservationValidationCode(StrEnum):
    MISSING_DATE       = "missing_date"
    PAST_DATE          = "past_date"
    MISSING_TIME       = "missing_time"
    MISSING_PARTY_SIZE = "missing_party_size"
    PARTY_TOO_LARGE    = "party_too_large"
    MISSING_NAME       = "missing_name"
    MISSING_PHONE      = "missing_phone"
    MISSING_SEATING    = "missing_seating"
    TERRACE_TOO_LARGE  = "terrace_too_large"
```

Raised by `ReservationDraftService.validate_ready_to_confirm()` and
caught by `telegram_router.py` to produce a localized error message.
