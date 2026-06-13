"""ZoneRepository — loads data/restaurant_info.json delivery.areas.

Placeholder entries matching ^[.*]$ are stripped with a single WARN log.
The in-memory list powers the rapidfuzz zone-check tool; the Postgres
upsert makes zones visible to the dispatcher dashboard.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeliveryZone

logger = logging.getLogger(__name__)

_INFO_PATH = Path("data/restaurant_info.json")
_PLACEHOLDER_RE = re.compile(r"^\[.*\]$")

_zone_cache: list[str] = []


def load_zones() -> None:
    """Load delivery areas into memory. Called once at startup."""
    with open(_INFO_PATH, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    areas: list[str] = (
        data.get("restaurant", {}).get("delivery", {}).get("areas", [])
    )
    placeholders = [a for a in areas if _PLACEHOLDER_RE.match(a)]
    if placeholders:
        logger.warning(
            "zone_placeholders_skipped",
            extra={"count": len(placeholders)},
        )
    _zone_cache.clear()
    _zone_cache.extend(a for a in areas if not _PLACEHOLDER_RE.match(a))
    logger.info("zones_loaded", extra={"count": len(_zone_cache)})


def list_areas() -> list[str]:
    return list(_zone_cache)


async def upsert_zones(session: AsyncSession) -> None:
    """Upsert zone list into delivery_zones. Idempotent."""
    if not _zone_cache:
        load_zones()
    rows = [{"area_name": area, "aliases": []} for area in _zone_cache]
    stmt = pg_insert(DeliveryZone).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["area_name"])
    await session.execute(stmt)
    await session.commit()
    logger.info("zones_upserted", extra={"count": len(rows)})
