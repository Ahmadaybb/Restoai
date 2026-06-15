"""image_service — menu lookup for image classifier predictions.

Kept in the services layer so telegram_router can call it without
importing app.repositories directly (architecture layering rule T046).
"""
from __future__ import annotations

from app.domain.menu import MenuItem
from app.infra.image_classifier import MENU_SEARCH_TERMS
from app.repositories import menu_repo


def find_menu_item_for_class(class_name: str) -> MenuItem | None:
    """Return the best-matching MenuItem for a classifier class name.

    Priority:
    1. Exact match on display name (e.g. "Sfiha" == "Sfiha")
    2. Exact match on raw class name (e.g. "kabab" == "Kabab")
    3. Contains match on the search term (fallback for compound names)
    """
    from app.infra.image_classifier import DISPLAY_NAMES
    items = menu_repo.get_menu()
    display = DISPLAY_NAMES.get(class_name, class_name).lower()
    term = MENU_SEARCH_TERMS.get(class_name, class_name).lower()

    # Pass 1: exact match on display name
    for item in items:
        if item.name_en.lower() == display:
            return item

    # Pass 2: exact match on raw class name
    for item in items:
        if item.name_en.lower() == class_name.lower():
            return item

    # Pass 3: contains fallback
    return next((item for item in items if term in item.name_en.lower()), None)
