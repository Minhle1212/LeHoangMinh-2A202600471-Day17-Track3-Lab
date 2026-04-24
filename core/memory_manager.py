import time
from typing import Any

from memory_backends import (
    BaseMemory,
    ChromeHistoryMemory,
    ConversationBufferMemory,
    JSONEpisodicMemory,
    RedisMemory,
)


class MemoryManager:
    """Unified memory manager with context window management.

    Coordinates all 4 memory backends and manages context window limits
    using priority-based hierarchical eviction.
    """

    def __init__(
        self,
        session_id: str,
        max_total_tokens: int = 4000,
        max_recent_messages: int = 10,
        priority_levels: dict[str, int] | None = None,
        redis_config: dict | None = None,
        chrome_config: dict | None = None,
    ):
        self.session_id = session_id
        self.max_total_tokens = max_total_tokens
        self.max_recent_messages = max_recent_messages
        self.priority_levels = priority_levels or {
            "system": 3,
            "assistant": 2,
            "user": 1,
        }

        self.buffer = ConversationBufferMemory(session_id)
        self.episodic = JSONEpisodicMemory(session_id)
        self.redis = RedisMemory(
            session_id, **(redis_config or {})
        )
        self.chrome = ChromeHistoryMemory(
            session_id, **(chrome_config or {})
        )

        self._backends = {
            "buffer": self.buffer,
            "episodic": self.episodic,
            "redis": self.redis,
            "chrome": self.chrome,
        }

        self._episode_started = False

    def add_message(self, role: str, content: str) -> None:
        """Add a message to all applicable memory backends."""
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
        }
        self.buffer.add(message)
        self.episodic.add(message)
        self.redis.add(message)

    def end_turn(self, mood: str = "neutral") -> None:
        """End the current conversation turn, finalizing episodic episode."""
        self.episodic.end_episode(mood=mood)
        self._episode_started = False

    def get_context(self, system_prompt: str = "") -> list[dict]:
        """Build a context window respecting token limits via priority eviction.

        Priority hierarchy:
        1. System prompt (always included)
        2. Recent messages from buffer (up to max_recent_messages)
        3. Retrieved episodic memories (if space allows)
        4. Retrieved long-term Redis memories (if space allows)
        """
        context = []
        total_tokens = 0

        system_entry = {
            "role": "system",
            "content": system_prompt or "You are a helpful AI assistant.",
            "priority": self.priority_levels["system"],
        }
        context.append(system_entry)
        total_tokens += len(system_prompt) // 4

        recent = self.buffer.get_recent(self.max_recent_messages)
        for msg in recent:
            priority = self.priority_levels.get(msg["role"], 0)
            tokens = len(msg["content"]) // 4
            if total_tokens + tokens <= self.max_total_tokens:
                context.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "priority": priority,
                })
                total_tokens += tokens

        episodic = self.episodic.get_recent(3)
        for ep in episodic:
            summary_text = ep.get("summary", "")
            tokens = len(summary_text) // 4
            if total_tokens + tokens <= self.max_total_tokens:
                context.append({
                    "role": "system",
                    "content": f"[Episodic memory] {summary_text}",
                    "priority": 0,
                })
                total_tokens += tokens

        redis_msgs = self.redis.get_recent(3)
        for msg in redis_msgs:
            tokens = len(msg["content"]) // 4
            if total_tokens + tokens <= self.max_total_tokens:
                context.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "priority": 0,
                })
                total_tokens += tokens

        return self._evict_low_priority(context)

    def search_all(self, query: str, top_k: int = 5) -> dict[str, list]:
        """Search across all memory backends for the given query."""
        results = {
            "buffer": self.buffer.search(query, top_k),
            "episodic": self.episodic.search(query, top_k),
            "redis": self.redis.search(query, top_k),
            "chrome": self.chrome.search(query, top_k),
        }
        return results

    def get_all_stats(self) -> dict[str, Any]:
        """Return combined statistics from all backends."""
        stats = {}
        for name, backend in self._backends.items():
            stats[name] = backend.get_stats()
        stats["context_window"] = {
            "max_total_tokens": self.max_total_tokens,
            "max_recent_messages": self.max_recent_messages,
            "priority_levels": self.priority_levels,
        }
        return stats

    def clear_all(self) -> None:
        """Clear all memory backends."""
        for backend in self._backends.values():
            backend.clear()

    def _evict_low_priority(self, context: list[dict]) -> list[dict]:
        """Remove lowest-priority entries when token budget is exceeded."""
        if len(context) == 0:
            return context

        total_tokens = sum(
            len(entry["content"]) // 4 for entry in context
        )
        while total_tokens > self.max_total_tokens and len(context) > 1:
            min_priority = min(entry.get("priority", 0) for entry in context[1:])
            for i in range(1, len(context)):
                if context[i].get("priority", 0) == min_priority:
                    total_tokens -= len(context[i]["content"]) // 4
                    context.pop(i)
                    break
        return context
