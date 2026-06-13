"""MenuRepository — loads data/menu_full_ar.json into memory and Postgres.

Items in the JSON have no id field; a stable id is generated from
group+name slugification. The in-memory cache is the hot path for all
runtime lookups; the Postgres upsert runs once at startup so the
dispatcher dashboard sees consistent data.
"""
import json
import logging
import re
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MenuChunk as MenuChunkORM
from app.db.models import MenuItem as MenuItemORM
from app.domain.menu import MenuChunk, MenuItem

logger = logging.getLogger(__name__)

_MENU_PATH = Path("data/menu_full_ar.json")
_FUZZY_THRESHOLD = 50

_menu_cache: dict[str, MenuItem] = {}


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "_", text).strip("_")


def _make_id(group: str, name: str, seen: set[str]) -> str:
    base = _slugify(f"{group}_{name}") if group else _slugify(name)
    if not base:
        base = "item"
    candidate = base
    counter = 2
    while candidate in seen:
        candidate = f"{base}_{counter}"
        counter += 1
    seen.add(candidate)
    return candidate


def _json_to_domain(raw: dict[str, Any], item_id: str) -> MenuItem:
    return MenuItem(
        id=item_id,
        category=raw.get("category", ""),
        name_en=raw.get("name", ""),
        name_ar=raw.get("name_ar", ""),
        name_translit=None,
        description_en=raw.get("description") or None,
        description_ar=raw.get("description_ar") or None,
        price_usd=Decimal(str(raw.get("price_usd", 0))),
        available=bool(raw.get("is_available", True)),
        spice_level=None,
        tags=[],
    )


def load_menu() -> None:
    """Load JSON corpus into the in-memory cache. Called once at startup."""
    with open(_MENU_PATH, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    items: list[dict[str, Any]] = data.get("menu", [])
    seen: set[str] = set()
    _menu_cache.clear()
    for raw in items:
        item_id = _make_id(raw.get("group", ""), raw.get("name", ""), seen)
        item = _json_to_domain(raw, item_id)
        _menu_cache[item_id] = item
    logger.info("menu_loaded", extra={"count": len(_menu_cache)})


def get_menu() -> list[MenuItem]:
    return list(_menu_cache.values())


def get_item(item_id: str) -> MenuItem | None:
    return _menu_cache.get(item_id)


def find_by_phrase(phrase: str) -> list[MenuItem]:
    """Fuzzy search over en + ar + translit names. Returns best matches."""
    if not _menu_cache:
        return []
    choices = {
        item_id: f"{item.name_en} {item.name_ar or ''} {item.name_translit or ''}"
        for item_id, item in _menu_cache.items()
    }
    results = process.extract(
        phrase, choices, scorer=fuzz.token_set_ratio, limit=5
    )
    return [
        _menu_cache[item_id]
        for _, score, item_id in results
        if score >= _FUZZY_THRESHOLD
    ]


async def upsert_chunks(
    session: AsyncSession, chunks: list[MenuChunk]
) -> None:
    """Upsert MenuChunk rows (keyed by menu_item_id + language). Idempotent.

    Called by app/cli/embed_menu.py after embedding. The unique constraint
    uq_menu_chunk_item_lang enforces the idempotency key.
    """
    rows = [
        {
            "id": chunk.id,
            "menu_item_id": chunk.menu_item_id,
            "text": chunk.text,
            "language": chunk.language,
            "embedding": chunk.embedding,
        }
        for chunk in chunks
        if chunk.embedding is not None
    ]
    if not rows:
        return
    stmt = pg_insert(MenuChunkORM).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_menu_chunk_item_lang",
        set_={
            "text": stmt.excluded.text,
            "embedding": stmt.excluded.embedding,
        },
    )
    await session.execute(stmt)
    await session.commit()
    logger.info("menu_chunks_upserted", extra={"count": len(rows)})


async def upsert_menu_items(session: AsyncSession) -> None:
    """Upsert all in-memory items into the menu_items table."""
    if not _menu_cache:
        load_menu()
    rows = [
        {
            "id": item.id,
            "category": item.category,
            "name_en": item.name_en,
            "name_ar": item.name_ar,
            "name_translit": item.name_translit,
            "description_en": item.description_en,
            "description_ar": item.description_ar,
            "price_usd": item.price_usd,
            "available": item.available,
            "spice_level": item.spice_level,
            "tags": item.tags,
        }
        for item in _menu_cache.values()
    ]
    stmt = pg_insert(MenuItemORM).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "category": stmt.excluded.category,
            "name_en": stmt.excluded.name_en,
            "name_ar": stmt.excluded.name_ar,
            "available": stmt.excluded.available,
            "price_usd": stmt.excluded.price_usd,
        },
    )
    await session.execute(stmt)
    await session.commit()
    logger.info("menu_items_upserted", extra={"count": len(rows)})
