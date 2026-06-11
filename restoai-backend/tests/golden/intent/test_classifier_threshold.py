"""CI gate: intent classifier macro F1 must be >= 0.93 on the frozen eval slice.

Constitution Principle II; research.md R5.
"""
import json
from pathlib import Path

import pytest

EVAL_SLICE = Path(__file__).parent / "eval_slice.jsonl"
MACRO_F1_THRESHOLD = 0.93


@pytest.mark.golden
def test_intent_classifier_macro_f1() -> None:
    from app.infra.intent_classifier import classify, load_classifier

    load_classifier()

    records = [
        json.loads(line)
        for line in EVAL_SLICE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    y_true = [r["intent"] for r in records]
    y_pred = [classify(r["text"])[0].value for r in records]

    # Compute per-class F1 then macro-average
    classes = sorted(set(y_true))
    f1_scores: list[float] = []
    for cls in classes:
        tp = sum(t == cls and p == cls for t, p in zip(y_true, y_pred))
        fp = sum(t != cls and p == cls for t, p in zip(y_true, y_pred))
        fn = sum(t == cls and p != cls for t, p in zip(y_true, y_pred))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        f1_scores.append(f1)

    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    assert macro_f1 >= MACRO_F1_THRESHOLD, (
        f"Intent classifier macro F1 {macro_f1:.4f} is below threshold "
        f"{MACRO_F1_THRESHOLD}. Per-class F1: "
        + ", ".join(f"{c}={s:.3f}" for c, s in zip(classes, f1_scores))
    )
