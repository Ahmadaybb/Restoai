"""One-off CLI: chunk the menu corpus, embed it, and upsert into Postgres.

Usage (from repo root, with the DB and embedder available):
    uv run python -m app.cli.embed_menu

Idempotent: upserts keyed by (menu_item_id, language) so re-runs are safe.
Per data-model.md §MenuChunk and research.md R2; T072.
"""
import asyncio
import logging

from app.domain.menu import MenuChunk, MenuItem
from app.infra.embed_client import EmbedderClient, load_embedder
from app.repositories import menu_repo

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64


def _build_chunks(item: MenuItem) -> list[MenuChunk]:
    """Build per-language text chunks for one menu item (EN + AR).

    Each chunk concatenates the item name, description, category, price, and
    any tags or spice level so the embedder sees a rich natural-language
    passage rather than a sparse JSON record.
    """
    chunks: list[MenuChunk] = []

    # English chunk
    en_parts: list[str] = [item.name_en]
    if item.description_en:
        en_parts.append(item.description_en)
    en_parts.append(f"Category: {item.category}")
    en_parts.append(f"Price: ${item.price_usd:.2f}")
    if item.spice_level and item.spice_level != "none":
        en_parts.append(f"Spice level: {item.spice_level}")
    if item.tags:
        en_parts.append(f"Tags: {', '.join(item.tags)}")
    chunks.append(MenuChunk(
        menu_item_id=item.id,
        text=". ".join(en_parts),
        language="en",
    ))

    # Arabic chunk — only when an Arabic name is present
    if item.name_ar and item.name_ar.strip():
        ar_parts: list[str] = [item.name_ar]
        if item.description_ar:
            ar_parts.append(item.description_ar)
        ar_parts.append(f"التصنيف: {item.category}")
        ar_parts.append(f"السعر: ${item.price_usd:.2f}")
        chunks.append(MenuChunk(
            menu_item_id=item.id,
            text=". ".join(ar_parts),
            language="ar",
        ))

    return chunks


async def embed_and_upsert() -> None:
    """Load menu → build chunks → embed in batches → upsert into Postgres."""
    from app.db.engine import get_session, init_engine
    from app.infra.settings import get_settings

    settings = get_settings()
    init_engine(settings.DATABASE_URL)

    menu_repo.load_menu()
    items = menu_repo.get_menu()
    logger.info("embedding_menu_start", extra={"item_count": len(items)})

    all_chunks: list[MenuChunk] = []
    for item in items:
        all_chunks.extend(_build_chunks(item))
    logger.info("chunks_built", extra={"chunk_count": len(all_chunks)})

    embedder = EmbedderClient()
    texts = [chunk.text for chunk in all_chunks]
    embeddings: list[list[float]] = []
    total_batches = (len(texts) + _BATCH_SIZE - 1) // _BATCH_SIZE

    for batch_idx in range(total_batches):
        batch = texts[batch_idx * _BATCH_SIZE : (batch_idx + 1) * _BATCH_SIZE]
        vecs = await embedder.embed_documents(batch)
        embeddings.extend(vecs)
        logger.info(
            "batch_embedded",
            extra={"batch": batch_idx + 1, "of": total_batches},
        )

    for chunk, vec in zip(all_chunks, embeddings):
        chunk.embedding = vec

    async for session in get_session():
        await menu_repo.upsert_chunks(session, all_chunks)
        break

    logger.info("embed_menu_complete", extra={"upserted": len(all_chunks)})


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_embedder()
    asyncio.run(embed_and_upsert())


if __name__ == "__main__":
    main()
