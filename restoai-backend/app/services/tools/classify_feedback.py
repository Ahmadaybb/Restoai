"""classify_feedback — sentiment classification for customer feedback."""
from app.domain.clients import LLMClient
from app.domain.feedback import Sentiment

_SYSTEM = (
    "You are a sentiment classifier for a Lebanese restaurant. "
    "Given a star rating (1-5) and an optional customer comment, "
    "classify the feedback as exactly one of: good, bad, neutral. "
    "Reply with ONLY the word: good, bad, or neutral. Nothing else."
)


async def classify_feedback(
    star_rating: int,
    comment: str | None,
    llm: LLMClient,
) -> Sentiment:
    """Use mechanical-tier LLM to classify feedback. Falls back to star heuristic on failure."""
    if comment is None:
        return _heuristic(star_rating)

    user = f"Star rating: {star_rating}/5\nComment: {comment}"
    try:
        result = await llm.complete_mechanical(system=_SYSTEM, user=user)
        cleaned = result.strip().lower()
        if cleaned in ("good", "bad", "neutral"):
            return Sentiment(cleaned)
    except Exception:  # noqa: BLE001
        pass

    return _heuristic(star_rating)


def _heuristic(star_rating: int) -> Sentiment:
    if star_rating >= 4:
        return Sentiment.GOOD
    if star_rating == 3:
        return Sentiment.NEUTRAL
    return Sentiment.BAD
