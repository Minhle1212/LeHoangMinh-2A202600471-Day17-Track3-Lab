import time
from collections import deque
from typing import Any

from .base import BaseMemory


class ConversationBufferMemory(BaseMemory):
    """Short-term in-memory conversation buffer.

    Stores messages in a rolling deque. Ideal for current session context.
    Messages have role and content. Supports timestamp-based priority.
    """

    def __init__(
        self,
        session_id: str,
        max_messages: int = 100,
        max_tokens: int = 4000,
        **kwargs,
    ):
        super().__init__(session_id, **kwargs)
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._buffer: deque[dict] = deque(maxlen=max_messages)
        self._token_counts: deque[int] = deque(maxlen=max_messages)
        self._access_order: deque[str] = deque(maxlen=max_messages)

    def add(self, message: dict) -> None:
        role = message.get("role", "user")
        content = message.get("content", "")
        token_count = self._estimate_tokens(content)
        timestamp = message.get("timestamp", time.time())

        entry = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "session_id": self.session_id,
            "memory_type": "buffer",
            "priority": self._compute_priority(role, timestamp),
            "id": f"{self.session_id}_{len(self._buffer)}",
        }
        self._buffer.append(entry)
        self._token_counts.append(token_count)
        self._access_order.append(entry["id"])
        self._auto_trim()

    def get_recent(self, n: int = 10) -> list[dict]:
        result = list(self._buffer)[-n:]
        for entry in result:
            self._access_order.append(entry["id"])
        return result

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_lower = query.lower()
        scored = []
        for entry in reversed(self._buffer):
            content_lower = entry["content"].lower()
            if query_lower in content_lower:
                score = content_lower.count(query_lower)
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def clear(self) -> None:
        self._buffer.clear()
        self._token_counts.clear()
        self._access_order.clear()

    def get_stats(self) -> dict[str, Any]:
        total_tokens = sum(self._token_counts)
        return {
            "type": "ConversationBufferMemory",
            "memory_type": "Short-term",
            "message_count": len(self._buffer),
            "total_tokens": total_tokens,
            "max_messages": self.max_messages,
            "max_tokens": self.max_tokens,
            "session_id": self.session_id,
        }

    def get_all(self) -> list[dict]:
        """Return all buffered messages sorted by timestamp."""
        return sorted(list(self._buffer), key=lambda x: x["timestamp"])

    def _auto_trim(self) -> None:
        while len(self._buffer) > 0 and sum(self._token_counts) > self.max_tokens:
            self._buffer.popleft()
        while len(self._buffer) > self.max_messages:
            self._buffer.popleft()

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def _compute_priority(self, role: str, timestamp: float) -> int:
        base = {"system": 3, "assistant": 2, "user": 1}.get(role, 0)
        recency_boost = 1 if (time.time() - timestamp) < 300 else 0
        return base + recency_boost
