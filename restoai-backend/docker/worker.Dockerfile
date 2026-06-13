FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

RUN UV_HTTP_TIMEOUT=120 uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

COPY app/ ./app/
COPY data/ ./data/

CMD ["sh", "-c", "uv run rq worker --with-scheduler --url $REDIS_URL default"]
