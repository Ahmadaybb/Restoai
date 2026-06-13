"""Load static restaurant config from data/restaurant_info.json (LRU-cached). ADR-014."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DEFAULT_PATH = Path("data/restaurant_info.json")


@lru_cache(maxsize=1)
def get_call_center_phone(path: Path = _DEFAULT_PATH) -> str:
    """Return the restaurant call-center phone number. Reads JSON once and caches. R5."""
    with open(path, encoding="utf-8") as fh:
        info = json.load(fh)
    return str(info["restaurant"]["contact"]["phone"])
