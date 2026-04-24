import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .base import BaseMemory


class JSONEpisodicMemory(BaseMemory):
    """Episodic memory backed by a JSON file.

    Stores conversation episodes as structured events. Each episode includes
    summary, timestamp, mood, and topic tags. Supports temporal queries.
    """

    def __init__(
        self,
        session_id: str,
        storage_path: str | None = None,
        max_episodes: int = 500,
        **kwargs,
    ):
        super().__init__(session_id, **kwargs)
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(__file__), "..", "data", f"episodes_{session_id}.json"
            )
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_episodes = max_episodes
        self._episodes: list[dict] = []
        self._current_episode: dict | None = None
        self._load()

    def add(self, message: dict) -> None:
        role = message.get("role", "user")
        content = message.get("content", "")
        timestamp = message.get("timestamp", time.time())

        if self._current_episode is None:
            self._start_new_episode(timestamp, role)

        self._current_episode["messages"].append({
            "role": role,
            "content": content,
            "timestamp": timestamp,
        })
        self._current_episode["message_count"] += 1
        self._current_episode["last_timestamp"] = timestamp

        if role == "user":
            self._current_episode["topic_tags"] = self._extract_topics(content)
            self._current_episode["summary"] = self._generate_summary(
                self._current_episode["messages"]
            )

    def end_episode(self, mood: str = "neutral", outcome: str = "") -> None:
        if self._current_episode is not None:
            self._current_episode["mood"] = mood
            self._current_episode["outcome"] = outcome
            self._current_episode["duration"] = (
                self._current_episode["last_timestamp"]
                - self._current_episode["start_timestamp"]
            )
            self._episodes.append(self._current_episode)
            self._current_episode = None
            self._save()
            self._auto_evict()

    def get_recent(self, n: int = 10) -> list[dict]:
        episodes = sorted(
            self._episodes, key=lambda x: x["start_timestamp"], reverse=True
        )[:n]
        result = []
        for ep in episodes:
            result.append({
                "episode_id": ep["episode_id"],
                "summary": ep["summary"],
                "topic_tags": ep["topic_tags"],
                "mood": ep.get("mood", "neutral"),
                "message_count": ep["message_count"],
                "timestamp": ep["start_timestamp"],
            })
        return result

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_lower = query.lower()
        scored = []
        for ep in self._episodes:
            score = 0
            summary_lower = ep.get("summary", "").lower()
            content_text = " ".join(m["content"].lower() for m in ep["messages"])
            tags = " ".join(ep.get("topic_tags", [])).lower()

            if query_lower in summary_lower:
                score += 5
            if query_lower in content_text:
                score += 3
            if query_lower in tags:
                score += 10

            if score > 0:
                scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "episode_id": ep["episode_id"],
                "summary": ep["summary"],
                "topic_tags": ep.get("topic_tags", []),
                "score": score,
            }
            for score, ep in scored[:top_k]
        ]

    def clear(self) -> None:
        self._episodes.clear()
        self._current_episode = None
        if self.storage_path.exists():
            self.storage_path.unlink()

    def get_stats(self) -> dict[str, Any]:
        return {
            "type": "JSONEpisodicMemory",
            "memory_type": "Episodic",
            "total_episodes": len(self._episodes),
            "max_episodes": self.max_episodes,
            "storage_path": str(self.storage_path),
            "session_id": self.session_id,
        }

    def _load(self) -> None:
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._episodes = data.get("episodes", [])

    def _save(self) -> None:
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(
                {"episodes": self._episodes, "session_id": self.session_id},
                f,
                indent=2,
                ensure_ascii=False,
            )

    def _start_new_episode(self, timestamp: float, trigger_role: str) -> None:
        self._current_episode = {
            "episode_id": f"ep_{int(timestamp * 1000)}",
            "start_timestamp": timestamp,
            "last_timestamp": timestamp,
            "messages": [],
            "message_count": 0,
            "summary": "",
            "topic_tags": [],
            "trigger_role": trigger_role,
            "memory_type": "episodic",
        }

    def _extract_topics(self, content: str) -> list[str]:
        keywords = {
            "code": ["code", "python", "function", "class", "debug", "api"],
            "data": ["data", "database", "query", "sql", "schema"],
            "config": ["config", "setting", "env", "variable", "parameter"],
            "error": ["error", "bug", "issue", "fail", "exception"],
            "project": ["project", "file", "folder", "directory", "repo"],
        }
        content_lower = content.lower()
        found = []
        for topic, words in keywords.items():
            if any(word in content_lower for word in words):
                found.append(topic)
        return found

    def _generate_summary(self, messages: list[dict]) -> str:
        if not messages:
            return ""
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        if user_msgs:
            first = user_msgs[0][:100]
            rest_count = len(user_msgs) - 1
            return f"{first}... (+{rest_count} more)" if rest_count > 0 else first
        return messages[0]["content"][:100]

    def _auto_evict(self) -> None:
        while len(self._episodes) > self.max_episodes:
            self._episodes.pop(0)
