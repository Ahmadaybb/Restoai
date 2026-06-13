"""Intent classifier — loads data/intent_classifier.joblib once at startup.

Classes: order, reservation, query, status, image (research.md R5).
Macro F1 0.9378 on the held-out set (model_card.json).

The CI gate in tests/golden/intent/test_classifier_threshold.py asserts
macro F1 >= 0.93 to guard against distribution shift.
"""
import logging
from pathlib import Path
from typing import Any

import joblib

from app.domain.language import Intent

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("data/intent_classifier.joblib")
_CONFIDENCE_THRESHOLD = 0.5

_classifier: Any = None


def load_classifier(path: Path | str = _DEFAULT_PATH) -> None:
    global _classifier
    logger.info("loading_intent_classifier", extra={"path": str(path)})
    _classifier = joblib.load(path)
    logger.info("intent_classifier_loaded")


def is_loaded() -> bool:
    return _classifier is not None


def classify(text: str) -> tuple[Intent, float]:
    """Return (Intent, confidence). Falls back to Intent.UNKNOWN below threshold."""
    if _classifier is None:
        raise RuntimeError(
            "Intent classifier not loaded; call load_classifier() first."
        )

    label: str = str(_classifier.predict([text])[0])

    try:
        proba_array = _classifier.predict_proba([text])[0]
        classes: list[str] = list(_classifier.classes_)
        confidence = float(proba_array[classes.index(label)]) if label in classes else 0.0
    except AttributeError:
        # LinearSVC lacks predict_proba; use decision_function margin instead.
        decisions = _classifier.decision_function([text])[0]
        if hasattr(decisions, "__len__"):
            raw = float(max(decisions))
        else:
            raw = float(decisions)
        confidence = min(1.0, max(0.0, (raw + 1.0) / 2.0))

    if confidence < _CONFIDENCE_THRESHOLD:
        return Intent.UNKNOWN, confidence

    try:
        intent = Intent(label)
    except ValueError:
        intent = Intent.UNKNOWN

    return intent, confidence
