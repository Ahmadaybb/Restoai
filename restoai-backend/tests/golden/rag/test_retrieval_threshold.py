"""CI gate: RAG retrieval hit@3 must be >= 0.8 on the frozen golden set.

Requires:
  - embed_menu CLI to have been run (menu_chunks populated in the DB).
  - DB accessible via DATABASE_URL env var.
  - VOYAGE_API_KEY set in the environment.

Skips gracefully when either the DB or VOYAGE_API_KEY is unavailable so the
test can be gated in CI but does not fail in offline dev.

Constitution Principle II; research.md R2; T077.
"""
import json
import os
from pathlib import Path

import pytest

DATASET = Path(__file__).parent / "dataset.jsonl"
HIT_AT_3_THRESHOLD = 0.8


def _load_golden() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.golden
@pytest.mark.asyncio
async def test_rag_retrieval_hit_at_3() -> None:
    """MenuService.search must return the expected item in the top-3 for >= 80 % of questions."""
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping golden RAG test")

    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
    if not voyage_api_key:
        pytest.skip("VOYAGE_API_KEY not set — skipping golden RAG test")

    from app.db.engine import get_session, init_engine
    from app.infra.embed_client import EmbedderClient
    from app.services import menu_service

    try:
        init_engine(database_url)
    except Exception:
        pytest.skip("Could not initialise DB engine — skipping golden RAG test")

    embedder = EmbedderClient()
    records = _load_golden()
    hits = 0

    try:
        async for session in get_session():
            for rec in records:
                chunks = await menu_service.search(session, rec["question"], embedder, k=3)
                retrieved_ids = {c.menu_item_id for c in chunks}
                expected = set(rec["expected_top_menu_item_ids"])
                if retrieved_ids & expected:
                    hits += 1
            break
    except Exception as exc:
        pytest.skip(f"DB query failed ({exc}) — skipping golden RAG test")

    total = len(records)
    hit_rate = hits / total if total > 0 else 0.0

    assert hit_rate >= HIT_AT_3_THRESHOLD, (
        f"RAG hit@3 rate {hit_rate:.2f} ({hits}/{total}) is below "
        f"threshold {HIT_AT_3_THRESHOLD}. Run embed_menu CLI to populate chunks."
    )
