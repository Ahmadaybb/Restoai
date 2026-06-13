# Runbook: RestoAI Backend

Operational reference for the RestoAI backend service.
For a first-time setup walkthrough see
[`specs/001-takeaway-orders/quickstart.md`](specs/001-takeaway-orders/quickstart.md).

---

## Start / stop

```bash
# First run — builds images and applies migrations
docker compose up --build

# Subsequent runs (images already built)
docker compose up

# Run in the background
docker compose up -d

# Stop all services (data volumes preserved)
docker compose down

# Stop and destroy all data — irreversible
docker compose down -v
```

Check that all services are healthy:

```bash
docker compose ps
# Every service should show "running (healthy)" or "exited (0)" for migrate.

curl http://localhost:8000/healthz   # → {"status":"ok"}
curl http://localhost:8000/readyz    # → {"status":"ready"} once DB + Redis are up
```

`/readyz` calls `app/services/readiness.py` which probes both the Postgres
connection and the Redis connection before returning 200. If either is
unavailable it returns 503 with a structured error body.

### Service dependency order

```
migrate (exits 0) → api, worker
db (healthy)      → migrate, api, worker
redis (healthy)   → api, worker
```

If `migrate` exits non-zero, `api` and `worker` will not start. Check
migration logs: `docker compose logs migrate`.

---

## Polling ↔ webhook switch

### Development (long-polling)

Leave `TELEGRAM_WEBHOOK_URL` blank in `.env`:

```dotenv
TELEGRAM_WEBHOOK_URL=
```

The bot starts in polling mode automatically. No public URL is needed.
Telegram updates arrive via repeated `getUpdates` calls from the bot process.

### Production (webhook)

Set the following in `.env`:

```dotenv
TELEGRAM_WEBHOOK_URL=https://your-domain.example.com
TELEGRAM_WEBHOOK_SECRET=<random-string-min-32-chars>
TELEGRAM_WEBHOOK_SECRET_PATH=<random-url-segment>
```

The webhook URL registered with Telegram is:

```
https://your-domain.example.com/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET_PATH>
```

After changing `.env`, restart the API container:

```bash
docker compose restart api
```

The app calls `setWebhook` at lifespan startup and `deleteWebhook` at
graceful shutdown. Verify the webhook is registered:

```bash
curl https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo
```

### Reverting webhook to polling

Set `TELEGRAM_WEBHOOK_URL=` (blank) and restart. The lifespan handler will
call `deleteWebhook` before stopping the previous instance and will then
start polling.

---

## RQ queue inspection

```bash
# Summary of all queues
docker compose exec worker rq info --url $REDIS_URL

# List jobs in the default queue
docker compose exec worker rq jobs --url $REDIS_URL

# List failed jobs
docker compose exec worker rq failed --url $REDIS_URL

# Retry all failed jobs
docker compose exec worker rq requeue --all --url $REDIS_URL

# Retry a specific failed job by job ID
docker compose exec worker rq requeue --url $REDIS_URL <job-id>

# Clear all failed jobs (discard — use with care)
docker compose exec worker rq empty failed --url $REDIS_URL
```

RQ job definitions live in `app/workers/jobs.py`. The two registered jobs are:

| Job | Trigger | Purpose |
|-----|---------|---------|
| `dispatcher_notify` | `EscalationService.register_failure()` (3rd failure) | Logs escalation event for the dispatcher dashboard |

Jobs are enqueued best-effort (`_try_enqueue_notify` in `escalation_service.py`
swallows `Exception` silently). A failed or missing worker does **not** block
the customer-facing order flow.

---

## Secret rotation

### Rotate `DISPATCHER_API_TOKEN`

1. Generate a new token (e.g., `openssl rand -hex 32`).
2. Update `.env` (or the secrets manager) with the new value.
3. Restart the API container:
   ```bash
   docker compose restart api
   ```
4. Update the token in your dispatcher dashboard or API client.

Existing `DispatcherAction` rows store only a SHA-256 hash of the old token —
the hash does not need to be updated. Audit history is preserved.

### Rotate `TELEGRAM_BOT_TOKEN`

1. Go to `@BotFather` → `/mybots` → select bot → `API Token` → `Revoke`.
   The old token is immediately invalidated by Telegram.
2. Copy the new token into `.env`.
3. Restart the API container:
   ```bash
   docker compose restart api
   ```
   The lifespan handler re-registers the webhook (or restarts polling) with
   the new token.

### Rotate `GROQ_API_KEY`

1. Generate a new key in the Groq console.
2. Update `.env`.
3. Restart the API container:
   ```bash
   docker compose restart api
   ```
   No webhook registration is involved; the new key takes effect immediately.

### Rotate `DATABASE_URL` (connection string)

Changing only the password:

1. Update the Postgres password in `docker-compose.yml` environment or in the
   external secrets manager.
2. Update `DATABASE_URL` in `.env`.
3. Restart api + worker:
   ```bash
   docker compose restart api worker
   ```

---

## Single golden-set evaluation

Run classifier and RAG threshold tests against the running API container:

```bash
# Intent classifier — asserts macro F1 ≥ 0.93 on the eval slice
docker compose exec api pytest tests/golden/intent/test_classifier_threshold.py -v

# RAG retrieval — asserts hit@3 ≥ threshold on the menu Q&A golden set
docker compose exec api pytest tests/golden/rag/ -v
```

Or run both in one command:

```bash
docker compose exec api pytest tests/golden/ -v
```

These tests rely on the loaded embedding model and the Postgres `menu_chunks`
table populated from `data/menu_full_ar.json`. Both are ready once
`/readyz` returns 200.

### Full test suite

```bash
# All unit + integration + e2e + golden tests
docker compose exec api pytest -q

# Only end-to-end happy-path tests
docker compose exec api pytest tests/e2e/ -v
```

---

## Migration rollback

```bash
# Show migration history
docker compose run --rm migrate alembic history --verbose

# Downgrade one revision (undo the most recent migration)
docker compose run --rm migrate alembic downgrade -1

# Downgrade to a specific revision ID
docker compose run --rm migrate alembic downgrade <revision_id>

# Show current revision applied to the DB
docker compose run --rm migrate alembic current
```

**Before rolling back in production**:
1. Confirm no application traffic is hitting the DB (scale api + worker to 0).
2. Take a Postgres snapshot / backup.
3. Run the downgrade.
4. Re-deploy the previous image version.

---

## Log inspection

All services emit structured JSON logs to stdout. View them with:

```bash
# Stream all service logs
docker compose logs -f

# API logs only
docker compose logs -f api

# Filter for errors only (jq required)
docker compose logs api | jq 'select(.level == "ERROR")'

# Trace a single request by request_id
docker compose logs api | jq 'select(.request_id == "<uuid>")'

# Cost log entries (LLM usage)
docker compose logs api | jq 'select(.event == "llm_cost")'
```

Key structured fields:

| Field | Type | Meaning |
|-------|------|---------|
| `request_id` | UUID | Correlation ID — set per HTTP request by `RequestIdMiddleware` |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `event` | string | Log message / event name |
| `customer_id` | UUID | Redacted where required |
| `llm_cost` | object | `model`, `tier`, `input_tokens`, `output_tokens`, `est_cost_usd` |

---

## Troubleshooting

### API container keeps restarting

Check logs for a `Settings()` validation error:

```bash
docker compose logs api | tail -30
```

Common causes:
- `TELEGRAM_BOT_TOKEN` not set — hard boot failure by design (Principle V).
- `GROQ_API_KEY` not set.
- `DATABASE_URL` or `REDIS_URL` pointing to unreachable hosts.

### `/readyz` returns 503

One or both of DB / Redis is not responding. Check:

```bash
docker compose ps db redis
docker compose logs db redis
```

### Telegram updates not arriving (webhook mode)

1. Verify `TELEGRAM_WEBHOOK_URL` is publicly reachable over HTTPS.
2. Check that the secret path matches: `GET /telegram/webhook/<TELEGRAM_WEBHOOK_SECRET_PATH>` should return 405 (wrong method), not 404.
3. Check webhook status:
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
   ```
   Look for `"last_error_message"` in the response.

### RQ worker jobs not running

Check the worker container is healthy and connected to Redis:

```bash
docker compose logs worker
docker compose exec worker rq info --url $REDIS_URL
```

Job failures are visible in the failed queue; retry with `rq requeue --all`.
