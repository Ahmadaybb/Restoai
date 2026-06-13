"""MenuService — RAG search over menu_chunks (FR-007).

search() embeds the query via EmbeddingClient and runs a pgvector cosine
distance query against menu_chunks. The embedder is the local
intfloat/multilingual-e5-large (research.md R2); the caller supplies it
so the service remains testable with a fake embedder.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clients import EmbeddingClient
from app.domain.menu import MenuChunk, MenuItem
from app.repositories import menu_repo

logger = logging.getLogger(__name__)


def get_item(menu_item_id: str) -> MenuItem | None:
    """Return the MenuItem for *menu_item_id*, or None if not found."""
    return menu_repo.get_item(menu_item_id)


async def search(
    session: AsyncSession,
    query: str,
    embedder: EmbeddingClient,
    k: int = 3,
) -> list[MenuChunk]:
    """Embed *query* and return the top-*k* closest MenuChunk rows.

    Uses pgvector cosine distance (`<=>`) over the `menu_chunks` table.
    Returns an empty list when the table is empty (e.g., embed_menu has
    not been run yet) — the caller should handle this as a no-info case.

    FR-007; research.md R2; data-model.md §MenuChunk.
    """
    vec = await embedder.embed_query(query)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    sql = text(
        "SELECT id, menu_item_id, text, language "
        "FROM menu_chunks "
        "ORDER BY embedding <=> CAST(:q AS vector) "
        "LIMIT :k"
    )
    result = await session.execute(sql, {"q": vec_str, "k": k})
    rows = result.fetchall()

    logger.info(
        "menu_search_complete",
        extra={"query_len": len(query), "hits": len(rows)},
    )

    return [
        MenuChunk(
            id=row.id,
            menu_item_id=row.menu_item_id,
            text=row.text,
            language=row.language,
        )
        for row in rows
    ]
