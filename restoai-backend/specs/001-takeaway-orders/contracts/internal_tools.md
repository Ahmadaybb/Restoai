# Internal Tool Contracts (LLM-callable surfaces)

**Feature**: `001-takeaway-orders`

The conversation orchestrator routes customer messages to a small set of
internal tools. Each tool has a Pydantic input model and a Pydantic
output model — these are the boundary contracts Principle I mandates.
Tools are defined in `app/domain/tools.py` and implemented in
`app/services/`.

The tool registry is the *only* interface the synthesis-tier LLM is
allowed to call via function/tool calling. Tools call the cheap-tier LLM
internally where extraction is needed.

## Tool: `parse_order`

**Purpose**: Convert free-text into a list of `OrderItem` candidates.
Spec mapping: FR-003, FR-005, FR-006.

**Input** (`ParseOrderIn`):
```json
{"text": "2 hummus, 1 fattoush, no onions please", "language": "en"}
```

**Output** (`ParseOrderOut`):
```json
{
  "items": [
    {"menu_item_id": "hummus_classic", "quantity": 2, "customizations": []},
    {"menu_item_id": "fattoush", "quantity": 1,
     "customizations": [{"kind": "remove", "text": "no onions"}]}
  ],
  "unresolved": [],
  "confidence": 0.94
}
```

- `unresolved` is a list of strings the parser could not map. The
  conversation service uses this to ask follow-up questions (FR-006) and
  increments the `order_parse` failure counter when non-empty.
- `confidence` < 0.5 ⇒ the conversation service treats the result as a
  failure for the 3-strike counter.
- **Pipeline contract**: `parse_order` attempts to resolve each phrase to
  a `menu_item_id` using an internal fuzzy lookup against the menu
  corpus. Phrases that score below the resolution threshold are placed
  in `unresolved` with their original text preserved. The conversation
  service then calls `match_dish` on each unresolved phrase individually
  to attempt a second-pass resolution with alternatives surfaced. Only
  after `match_dish` also fails does the service prompt the customer for
  clarification and increment the failure counter.

## Tool: `match_dish`

**Purpose**: Resolve an ambiguous item phrase to a single menu item.
Spec mapping: FR-005.

**Input**: `{"phrase": "the chicken plate", "language": "en"}`

**Output**:
```json
{"menu_item_id": "grilled_chicken", "score": 0.86, "alternatives":
  [{"menu_item_id": "shish_taouk", "score": 0.71}]}
```

`score` < calibrated threshold ⇒ failure (`dish_match` counter).

## Tool: `answer_menu_question`

**Purpose**: RAG-grounded answer about a menu item or category. Spec
mapping: FR-007, FR-008.

**Input**: `{"question": "what's in the fattoush?", "language": "en"}`

**Output**:
```json
{
  "answer": "Fattoush is a Lebanese salad with romaine, tomato, ...",
  "citations": [{"menu_item_id": "fattoush", "chunk_id": "..."}]
}
```

Behavior contracts:
- Retrieval runs against the local `multilingual-e5-large` embedder
  (loaded once at app startup and offloaded via `asyncio.to_thread`),
  followed by a pgvector `ORDER BY embedding <-> :q LIMIT k` query.
  There is no external embedding API call on this path; embedder
  failures are local-only (e.g., model not loaded) and surface as
  `ExternalDependencyError` for the FR-034 degradation handler.
- The synthesis tier is instructed to **only** answer from
  `citations`. If retrieval is empty, the tool returns
  `{"answer": "I don't have info on that — let me show you what we do
  have.", "citations": []}` and the conversation service falls back to
  offering closest items (FR-007).

## Tool: `extract_address`

**Purpose**: Pull a structured address from a customer message.
Spec mapping: FR-010, FR-035.

**Input**: `{"text": "deliver to Hamra Street near AUB", "language": "en"}`

**Output**:
```json
{"kind": "text", "text_value": "Hamra Street near AUB",
 "area_label": "Hamra", "area_confidence": 0.91}
```

If `area_confidence` < 0.7 ⇒ `area_label = null`; the zone check is
recorded as "not confident → don't warn" per R8 in `research.md`.

## Tool: `check_zone`

**Purpose**: Decide in-zone vs. out-of-zone. Pure function over the
configured zone list. Spec mapping: FR-035.

**Input**: `{"area_label": "Hamra"}`

**Output**: `{"in_zone": true, "matched_entry": "Hamra"}` or
`{"in_zone": false, "matched_entry": null}`.

## Tool: `detect_language`

**Purpose**: Classify the language of one customer turn. Spec mapping:
FR-028.

**Input**: `{"text": "..."}` Output: `{"language": "en" | "ar_lb" |
"arabizi", "confidence": 0.0..1.0}`.

Implementation: fast script/n-gram heuristic first, cheap-tier LLM only
on ambiguity to keep cost low (Principle IV).

## Tool: `render_readback`

**Purpose**: Localized order read-back text for the confirmation gate.
Spec mapping: FR-016.

**Input**: `{"draft": OrderDraft, "language": "en"}` — the deserialized
OrderDraft domain model (not the raw Redis blob). Callers must
deserialize from Redis before passing to this tool.

**Output**: `{"text": "Here's your order: ...\nTotal: $24.50 (estimated;
final pricing is confirmed by the dispatcher).", "buttons":
[{"label": "✅ Confirm", "callback_data": "confirm:<draft_id>"},
{"label": "✏️ Edit", "callback_data": "edit:<draft_id>"}]}`.

The "estimated; final pricing…" line is the wording mandated by the
Pricing model assumption.

## Tool: `summarize_for_dispatcher`

**Purpose**: Generate a one-line summary of an escalated conversation
for the dispatcher escalation queue. Spec mapping: FR-025.

**Input**: `{"transcript": list[Turn], "draft": OrderDraft | None}`

**Output**: `{"summary": "Customer struggled to give a clear address;
2 hummus + 1 fattoush in cart, delivery; no confirmation yet."}`

## Tool registry tier assignments

| Tool | LLM tier called internally |
|---|---|
| `parse_order` | mechanical |
| `match_dish` | mechanical |
| `answer_menu_question` | synthesis (with retrieval pre-step) |
| `extract_address` | mechanical |
| `check_zone` | none (pure) |
| `detect_language` | mechanical (only on ambiguity) |
| `render_readback` | synthesis |
| `summarize_for_dispatcher` | synthesis |

This split is the implementation of Principle IV's cost-tier discipline.
A code-review check (a unit test that introspects the registry) enforces
that `mechanical` tools never invoke the synthesis client and vice
versa.
