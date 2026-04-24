from abc import ABC, abstractmethod
from typing import Any


class BaseMemory(ABC):
    """Abstract base class for all memory backends."""

    def __init__(self, session_id: str, **kwargs):
        self.session_id = session_id

    @abstractmethod
    def add(self, message: dict) -> None:
        """Add a message to memory."""
        pass

    @abstractmethod
    def get_recent(self, n: int = 10) -> list[dict]:
        """Retrieve the n most recent messages."""
        pass

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search across stored memories."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all memory for the session."""
        pass

    def get_stats(self) -> dict[str, Any]:
        """Return backend-specific statistics."""
        return {}
