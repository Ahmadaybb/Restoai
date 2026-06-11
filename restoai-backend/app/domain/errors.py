from enum import StrEnum


class ExternalDependencyError(Exception):
    """Raised when an external system (Groq, Redis, DB, Telegram) fails."""

    def __init__(self, dependency: str, message: str) -> None:
        self.dependency = dependency
        super().__init__(f"[{dependency}] {message}")


class OrderValidationCode(StrEnum):
    EMPTY_CART = "EMPTY_CART"
    MISSING_FULFILLMENT = "MISSING_FULFILLMENT"
    MISSING_ADDRESS = "MISSING_ADDRESS"
    ITEM_UNAVAILABLE = "ITEM_UNAVAILABLE"


class OrderValidationError(Exception):
    """Raised when an OrderDraft fails pre-confirmation validation."""

    def __init__(self, code: OrderValidationCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


class DispatcherAuthError(Exception):
    """Raised when a dispatcher request fails authentication or body validation."""


class DispatcherNameMissing(DispatcherAuthError):
    """dispatcher_name field missing or blank on a mutation endpoint."""
