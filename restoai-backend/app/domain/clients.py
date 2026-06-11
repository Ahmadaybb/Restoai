"""Protocol interfaces for external clients.

Implementations live in app/infra/. Tests inject hand-written fakes that
satisfy these protocols — no unittest.mock.patch needed.
"""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal surface that services depend on for LLM calls."""

    async def complete_mechanical(
        self,
        *,
        system: str,
        user: str,
        response_format: type[Any] | None = None,
    ) -> str:
        """Call the cheap/fast model tier. Returns the assistant reply text."""
        ...

    async def complete_synthesis(
        self,
        *,
        system: str,
        user: str,
        response_format: type[Any] | None = None,
    ) -> str:
        """Call the stronger synthesis model tier. Returns the assistant reply text."""
        ...


@runtime_checkable
class EmbeddingClient(Protocol):
    """Minimal surface for embedding operations."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Returns a float vector."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents. Returns one vector per text."""
        ...


@runtime_checkable
class MessengerClient(Protocol):
    """Minimal surface for sending messages to customers."""

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """Send a text message, optionally with inline keyboard buttons."""
        ...

    async def send_contact_request(self, *, chat_id: int) -> None:
        """Ask the customer to share their phone number."""
        ...
