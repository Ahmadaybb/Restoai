<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
[specs/001-takeaway-orders/plan.md](specs/001-takeaway-orders/plan.md).

Related artifacts for this feature:
- Spec: [specs/001-takeaway-orders/spec.md](specs/001-takeaway-orders/spec.md)
- Phase 0 research: [specs/001-takeaway-orders/research.md](specs/001-takeaway-orders/research.md)
- Data model: [specs/001-takeaway-orders/data-model.md](specs/001-takeaway-orders/data-model.md)
- Contracts: [specs/001-takeaway-orders/contracts/](specs/001-takeaway-orders/contracts/)
- Quickstart: [specs/001-takeaway-orders/quickstart.md](specs/001-takeaway-orders/quickstart.md)
- Project constitution: [.specify/memory/constitution.md](.specify/memory/constitution.md)
<!-- SPECKIT END -->

## Phase Gate Protocol

After every /speckit-implement phase completes, the following gate must
pass BEFORE running the next phase. No exceptions.

### Step 1 — Human Code Review
Send the completion report to the advisor for review.
Do NOT proceed until the advisor explicitly says "Phase N is approved."

### Step 2 — Local Tests
Run tests scoped to the phase that just completed:

Phase 1 (Setup):
  ruff check . && mypy app/domain app/services app/api app/infra

Phase 2 (Foundational):
  pytest tests/infra/ tests/architecture/ tests/services/test_tool_tier_enforcement.py -v

Phase 3 (US1):
  pytest tests/domain/ tests/api/ tests/services/ tests/e2e/test_us1_happy_path.py -v

Phase 4 (US2):
  pytest tests/golden/rag/ tests/services/test_no_fabrication.py tests/services/test_qa_preserves_draft.py -v

Phase 5 (US3):
  pytest tests/services/test_readback_customizations.py tests/api/test_dispatcher_customizations.py tests/services/test_unmapped_customization.py -v

Phase 6 (US4):
  pytest tests/e2e/test_us4_returning_customer.py -v

Phase 7 (US5):
  pytest tests/e2e/test_us5_escalation.py tests/services/test_no_callout_prompts.py -v

All tests must pass before the next phase starts.
