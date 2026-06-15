"""Image classifier for food recognition — EfficientNet-B0, 9 Lakkis Farm dish classes.

Loads weights from img_classifier/restoai_classifier.pth at startup.
Exposes predict(image_bytes) -> (class_name, confidence).
Val accuracy: 84.85% (restoai_model_card.json).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_PATH = Path("img_classifier/restoai_classifier.pth")
_MODEL_CARD_PATH = Path("img_classifier/restoai_model_card.json")

DISPLAY_NAMES: dict[str, str] = {
    "fatoush": "Fattoush",
    "fatteh": "Fatteh",
    "fokhara": "Fokhara (Clay Pot)",
    "kabab": "Kabab",
    "rawmeat": "Raw Meat Selection",
    "sfiha": "Sfiha",
    "taboule": "Tabbouleh",
    "tannour": "Tannour Bread",
    "tawook": "Tawook",
}

# Maps classifier class names → menu search terms where spellings differ
MENU_SEARCH_TERMS: dict[str, str] = {
    "fatoush": "fattoush",
    "taboule": "tabbouleh",
    "rawmeat": "raw meat",
    "tawook": "taouk",
}


class ImageClassifier:
    """Wraps EfficientNet-B0 for food image classification."""

    def __init__(self, model: object, class_names: list[str]) -> None:
        self._model = model
        self._class_names = class_names

    def predict(self, image_bytes: bytes) -> tuple[str, float]:
        """Return (class_name, confidence) for the given raw image bytes."""
        import io

        import torch
        from PIL import Image
        from torchvision import transforms

        transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = transform(img).unsqueeze(0)  # (1, 3, 224, 224)

        with torch.no_grad():
            logits = self._model(tensor)  # type: ignore[operator]
            probs = torch.softmax(logits, dim=1)[0]
            confidence, idx = probs.max(dim=0)

        class_name = self._class_names[int(idx)]
        return class_name, float(confidence)


def load_image_classifier() -> ImageClassifier | None:
    """Load EfficientNet-B0 weights at startup. Returns None if model is missing."""
    if not _MODEL_PATH.exists():
        logger.warning("image_classifier_not_found", extra={"path": str(_MODEL_PATH)})
        return None

    try:
        import torch
        from torchvision.models import efficientnet_b0

        with open(_MODEL_CARD_PATH, encoding="utf-8") as f:
            card: dict[str, object] = json.load(f)
        class_names: list[str] = list(card["class_names"])  # type: ignore[arg-type]
        num_classes = len(class_names)

        model = efficientnet_b0(weights=None)
        in_features: int = model.classifier[1].in_features  # type: ignore[index]
        model.classifier[1] = torch.nn.Linear(in_features, num_classes)  # type: ignore[index]

        state_dict = torch.load(_MODEL_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()

        logger.info("image_classifier_loaded", extra={"classes": class_names})
        return ImageClassifier(model, class_names)

    except Exception:
        logger.exception("image_classifier_load_failed")
        return None
