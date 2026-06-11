"""/healthz and /readyz endpoints.

/healthz — always returns 200 {"status":"ok"} (liveness).
/readyz  — returns 200 once DB, Redis, classifier, and embedder are all
           ready; 503 otherwise (readiness).

Per contracts/dispatcher_api.openapi.yaml health paths.
"""
import logging

from fastapi import APIRouter, Response

from app.infra.embed_client import is_loaded as embedder_loaded
from app.infra.intent_classifier import is_loaded as classifier_loaded
from app.services.readiness import check_db, check_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz(response: Response) -> dict[str, object]:
    checks: dict[str, bool] = {
        "db": await check_db(),
        "redis": await check_redis(),
        "classifier": classifier_loaded(),
        "embedder": embedder_loaded(),
    }
    all_ready = all(checks.values())
    if not all_ready:
        response.status_code = 503
    return {"status": "ready" if all_ready else "not_ready", "checks": checks}
