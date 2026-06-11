"""Structured JSON logging with PII redaction and request-id propagation.

Every log record is:
  1. Enriched with the current request_id from the ContextVar.
  2. Routed through redaction.redact() before emission.

Call configure_logging() once at app startup (done in app/main.py lifespan).
"""
import contextvars
import logging

from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[attr-defined]

from app.infra.redaction import redact

# Shared ContextVar — set by RequestIdMiddleware on every inbound request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class _RedactingJsonFormatter(JsonFormatter):
    def format(self, record: logging.LogRecord) -> str:
        record.__dict__.setdefault("request_id", request_id_var.get())
        formatted = super().format(record)
        return redact(formatted)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        _RedactingJsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
