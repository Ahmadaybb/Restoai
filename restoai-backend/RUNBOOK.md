# Runbook: RestoAI Backend

## Start / stop

```bash
# Start all services (builds images on first run)
docker compose up --build -d

# Stop all services (keeps volumes)
docker compose down

# Stop and destroy all data (volumes included) — destructive
docker compose down -v
```

Check status:

```bash
docker compose ps
curl http://localhost:8000/readyz
```

## Polling ↔ webhook switch

**Development (long-polling)** — leave `TELEGRAM_WEBHOOK_URL` blank in `.env`.
The bot starts in polling mode automatically.

**Production (webhook)** — set in `.env`:

```
TELEGRAM_WEBHOOK_URL=https://your-domain.example.com
TELEGRAM_WEBHOOK_SECRET=<random-string>
TELEGRAM_WEBHOOK_SECRET_PATH=<random-url-segment>
```

After changing, restart the API container:

```bash
docker compose restart api
```

The app calls `setWebhook` at lifespan startup when `TELEGRAM_WEBHOOK_URL` is set,
and deletes the webhook on shutdown.

## RQ queue inspection

```bash
# Open an RQ shell inside the worker container
docker compose exec worker rq info --url $REDIS_URL

# List failed jobs
docker compose exec worker rq failed --url $REDIS_URL

# Retry all failed jobs
docker compose exec worker rq requeue --all --url $REDIS_URL
```

## Secret rotation

1. Update `.env` (or the secrets manager entry) with the new value.
2. Restart the affected container:
   ```bash
   docker compose restart api worker
   ```
3. For `TELEGRAM_BOT_TOKEN`: the old token is immediately invalidated by Telegram;
   rotate it via `@BotFather` before restarting.

## Single golden-set evaluation

```bash
# Intent classifier threshold
docker compose exec api pytest tests/golden/intent/test_classifier_threshold.py -v

# RAG retrieval threshold
docker compose exec api pytest tests/golden/rag/test_retrieval_threshold.py -v
```

## Migration rollback

```bash
# Downgrade one step
docker compose run --rm migrate alembic downgrade -1

# Downgrade to a specific revision
docker compose run --rm migrate alembic downgrade <revision_id>

# View migration history
docker compose run --rm migrate alembic history --verbose
```
