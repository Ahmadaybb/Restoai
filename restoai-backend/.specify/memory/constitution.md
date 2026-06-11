<!--
Sync Impact Report
==================
Version change: TEMPLATE (uninitialized) → 1.0.0
Bump rationale: Initial ratification of the project constitution. All placeholder
tokens replaced with concrete RestoAI principles; no prior versioned content existed.

Modified principles: N/A (first ratification)
Added sections:
  - Core Principles (6 principles, replacing template's 5 placeholders)
    I.   Clean Architecture & Code Quality
    II.  Testing Standards & ML Evaluation Discipline
    III. Multilingual, Human-in-the-Loop UX
    IV.  Performance & Cost Discipline
    V.   Security & Data Integrity
    VI.  Documentation as a First-Class Deliverable
  - Operational Constraints (replaces SECTION_2 placeholder)
  - Development Workflow & Quality Gates (replaces SECTION_3 placeholder)
  - Governance (filled with tradeoff hierarchy, amendment, and deviation rules)
Removed sections: None

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — already references "Constitution Check"
     gate dynamically; no structural change required. Plan authors must derive
     gates from the six principles below.
  ✅ .specify/templates/spec-template.md — generic structure remains valid;
     multilingual + human-in-the-loop concerns enter via SC/FR per feature.
  ✅ .specify/templates/tasks-template.md — generic structure remains valid;
     principle-driven task categories (PII redaction tests, golden-set checks,
     cost logging, async enforcement) are inserted per feature, not in template.
  ⚠ README.md — not yet present in repo; expected per Principle VI.
  ⚠ ARCH.md, DECISIONS.md, RUNBOOK.md — not yet present; expected per Principle VI.

Follow-up TODOs: None deferred.
-->

# RestoAI Constitution

RestoAI is a multilingual AI-powered restaurant operations assistant for a
Lebanese restaurant. The principles below govern every specification, plan, and
task generated under this project. They are non-negotiable unless an explicit
deviation is recorded per the Governance section.

## Core Principles

### I. Clean Architecture & Code Quality

The codebase MUST follow Clean Architecture (Uncle Bob): strict separation
between entities, use cases, interface adapters, and frameworks & drivers. The
runtime layout MUST be:

- `app/api` — HTTP routing only; no business logic, no SQL.
- `app/services` — business logic and transaction boundaries.
- `app/repositories` — SQL only; never raises HTTP errors.
- `app/domain` — Pydantic domain models (entities, value objects).
- `app/infra` — adapters for external systems (LLMs, vector stores, blob
  storage, secrets).

Routers MUST NOT touch the database directly. Repositories MUST NOT raise HTTP
errors. Services MUST own transaction boundaries. Every function MUST have type
hints. Every external boundary (HTTP requests, LLM outputs, tool inputs, webhook
payloads) MUST use a Pydantic model. Routes, services, models, tools, and agent
code each live in their own modules — a 600-line `main.py` is a constitutional
violation.

**Rationale**: No vibe coding. Every line must be understood and defensible. A
layered codebase localizes change, makes review tractable, and prevents
HTTP/SQL/LLM concerns from leaking into each other.

### II. Testing Standards & ML Evaluation Discipline

Critical paths MUST be covered by automated tests:

- Each ML/RAG tool MUST be unit-tested in isolation with mocked LLMs.
- Pydantic schemas MUST be tested with both valid and invalid inputs.
- End-to-end tests MUST cover the main user flows with mocked external APIs.

Tests MUST run in CI on every push; manual-only test suites are forbidden
because they rot. ML components MUST have committed golden sets — a classifier
evaluation set and a RAG retrieval set — with committed thresholds. A
regression below threshold MUST fail CI.

ML/AI integrity rules (data leakage prevention) MUST be enforced:

- Preprocessing fits on the training split only.
- Three-way splits (train/validation/test) are mandatory for any model the
  product depends on.
- The test set is evaluated exactly once per reported result.
- Every reported metric MUST trace to the code that produced it.

**Rationale**: A wrong order costs money and trust. Tests that don't run
automatically don't exist. Data leakage produces ML metrics that lie.

### III. Multilingual, Human-in-the-Loop UX

Multilingual-first is non-negotiable. Every user-facing message, prompt,
validation, and error MUST work in English, Arabic (Lebanese dialect), and
Arabizi from the first commit of any feature — never bolted on later.

Restaurant-domain integrity outweighs latency: order accuracy MUST be preferred
over response speed when the two conflict.

High-stakes actions — orders, reservations, and customer-facing delivery
messages — MUST be confirmed by a human (dispatcher or call center) before the
AI fires the side effect. The AI MUST NOT silently commit any side effect a
human cannot undo.

Graceful degradation MUST be designed in: when an LLM, tool, or external API
fails, the user MUST receive a clear, localized message and a fallback path.
Stack traces, untranslated strings, and silent failures MUST NOT be exposed to
end users.

**Rationale**: The product is operated bilingually in a high-trust hospitality
setting. A wrong order is far more damaging than a slow one, and an
undoable autonomous action is worse than both.

### IV. Performance & Cost Discipline

Every LLM call MUST justify itself. Cheap models (Haiku-class, `gpt-4o-mini`,
Groq small) MUST be used for mechanical work (extracting tool arguments,
rewriting queries, routing). Stronger models are reserved for final synthesis
only.

Token usage and dollar cost MUST be logged per call and attributable to the
request that triggered it.

Caching MUST be used where it pays off: `lru_cache` for deterministic and
expensive computations (settings, model paths); TTL caches for tool responses
where the inputs and outputs are bounded (e.g., the same delivery-area query
within a 10-minute window).

Async is mandatory throughout the request path:

- FastAPI routes are async.
- Database calls use SQLAlchemy 2.x async or asyncpg.
- HTTP calls use `httpx.AsyncClient`.
- LLM SDK calls use async methods.
- `time.sleep` and `requests.get` are FORBIDDEN in any request path.

**Rationale**: LLM bills compound. Sync blocking in a request path silently
caps throughput and degrades p95 under load.

### V. Security & Data Integrity

All secrets MUST resolve from environment variables (and later, HashiCorp
Vault) at process startup. Secrets MUST NOT be hardcoded. The app MUST refuse
to start if a required secret is missing — failing fast at boot is preferred
over a runtime surprise.

No secrets, credentials, or virtual environments may be committed. `.gitignore`
hygiene is the minimum bar.

PII redaction MUST be enforced before customer phone numbers, names, or
addresses cross the service boundary in any log line, trace span, or LLM
prompt. A redaction test MUST exist that proves the redaction layer works on
representative inputs.

**Rationale**: Leaking customer PII into observability or third-party LLM
providers is the single fastest way to lose trust and break the law.

### VI. Documentation as a First-Class Deliverable

Documentation is a deliverable, not a courtesy:

- `DECISIONS.md` MUST record every architectural decision with rationale and
  the alternatives considered.
- `ARCH.md` MUST explain the architecture, not just how to run the project.
- `RUNBOOK.md` MUST describe how to start, stop, debug, and recover the system.
- `README.md` MUST be sufficient for a stranger to run the project in under
  five minutes.

Every technical choice (embedding model, chunking strategy, classifier model,
deployment target) MUST be backed by a number from a real evaluation — not by
"the tutorial said so."

**Rationale**: A system that can be re-derived from its docs is a system that
can be operated, audited, and handed off.

## Operational Constraints

The following constraints are derived from the principles above and apply to
every feature and plan generated under this constitution. They MUST be checked
by the Constitution Check gate of the `/speckit-plan` workflow:

- **Layered layout**: source MUST live under `app/api`, `app/services`,
  `app/repositories`, `app/domain`, `app/infra`. Cross-layer imports flow
  inward only (api → services → domain; infra implementations behind
  domain-defined protocols).
- **Boundary types**: all HTTP requests, HTTP responses, LLM outputs, tool
  inputs, and webhook payloads MUST be Pydantic models.
- **Async-only request path**: synchronous I/O (including `time.sleep`,
  `requests`, blocking DB drivers) is forbidden inside a request handler or
  any code reachable from one.
- **Secrets at startup**: a settings loader MUST validate required secrets at
  startup and refuse to boot on missing values.
- **PII redaction layer**: a single redaction utility MUST sit in front of
  logging, tracing, and LLM-prompt construction; bypassing it requires a
  documented exception.
- **Cost logging**: every LLM/embedding call MUST emit a structured record
  including model, input tokens, output tokens, and dollar cost, correlated to
  the originating request id.
- **Human confirmation**: any action that mutates an order, reservation, or
  outbound customer message MUST flow through a confirmation step owned by a
  human operator.

## Development Workflow & Quality Gates

- **CI gates**: every push MUST run linting, type checks, unit tests,
  integration tests with mocked externals, and ML golden-set evaluations.
  A regression in any gate blocks merge.
- **Constitution Check**: every plan MUST include a Constitution Check that
  enumerates how the proposed design satisfies Principles I–VI and the
  Operational Constraints above. Violations MUST be tracked in the plan's
  Complexity Tracking table and justified.
- **Decision log**: any architectural choice that affects more than one
  module — model selection, storage choice, framework adoption, schema shape
  — MUST land in `DECISIONS.md` in the same change that introduces it.
- **Evaluation evidence**: features that introduce or change an ML component
  (classifier, retriever, prompt template, model swap) MUST include the
  evaluation numbers that justify the change in the plan or its linked
  research artifact.
- **Code review**: reviewers MUST verify boundary types, layer purity (no
  router→DB shortcuts, no repo→HTTP errors), async correctness, and presence
  of redaction on any new logging or LLM call site.

## Governance

This constitution supersedes ad-hoc practices, individual preferences, and
prior conventions. It applies to every specification, plan, and task generated
under the Spec Kit workflow.

**Tradeoff hierarchy**: when principles conflict, the following order
arbitrates: **correctness > security > user experience > performance >
convenience**. A plan that trades correctness for performance is rejected; a
plan that trades convenience for security is approved.

**Amendment procedure**: amendments require (1) a written rationale, (2) a
version bump per the policy below, (3) an updated Sync Impact Report at the
top of this file, and (4) propagation to any dependent template, command, or
guidance document. Amendments are landed via the `/speckit-constitution`
workflow.

**Versioning policy** (semantic):

- **MAJOR**: a principle is removed, redefined in a backward-incompatible way,
  or the tradeoff hierarchy is reordered.
- **MINOR**: a new principle, section, or materially expanded guidance is
  added.
- **PATCH**: clarifications, wording improvements, or typo fixes that do not
  change meaning.

**Deviations**: any deviation from a principle in a specific feature MUST be
recorded as an entry in `DECISIONS.md` that names the principle deviated from,
the reason, the scope of the deviation, and the date it is expected to be
revisited. Undocumented deviations are constitutional violations.

**Compliance review**: the Constitution Check gate runs at plan time and is
re-verified after Phase 1 design. Reviewers are responsible for blocking
merges that violate this document without a recorded deviation.

**Version**: 1.0.0 | **Ratified**: 2026-06-09 | **Last Amended**: 2026-06-09
