"""Dispatcher authentication — bearer token + dispatcher_name enforcement.

research.md R12; contracts/dispatcher_api.openapi.yaml §DispatcherName.
Bearer token gates access; dispatcher_name on mutations provides audit attribution.
"""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infra.settings import get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

_NAME_CODE = "DISPATCHER_NAME_REQUIRED"


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> str:
    """Validate bearer token. Returns the raw token string."""
    settings = get_settings()
    if credentials.credentials != settings.DISPATCHER_API_TOKEN:
        logger.warning("dispatcher_auth_failed")
        raise HTTPException(status_code=401, detail="Invalid dispatcher token")
    return credentials.credentials


def validate_dispatcher_name(dispatcher_name: str | None) -> str:
    """Validate and return trimmed dispatcher_name. Raises 400 if invalid."""
    if not dispatcher_name:
        raise HTTPException(
            status_code=400,
            detail={"code": _NAME_CODE, "message": "dispatcher_name is required"},
        )
    trimmed = dispatcher_name.strip()
    if not trimmed:
        raise HTTPException(
            status_code=400,
            detail={"code": _NAME_CODE, "message": "dispatcher_name must not be blank"},
        )
    if len(trimmed) > 80:
        raise HTTPException(
            status_code=400,
            detail={"code": _NAME_CODE, "message": "dispatcher_name must be ≤80 characters"},
        )
    return trimmed
