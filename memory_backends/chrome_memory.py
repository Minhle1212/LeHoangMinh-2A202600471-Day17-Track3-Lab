import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .base import BaseMemory


class ChromeHistoryMemory(BaseMemory):
    """Semantic memory backed by Chrome browser history.

    Reads browsing history from Chrome's SQLite database to provide
    context about user's past web searches and visited pages.
    """

    def __init__(
        self,
        session_id: str,
        history_path: str | None = None,
        days_back: int = 30,
        max_visits: int = 1000,
        **kwargs,
    ):
        super().__init__(session_id, **kwargs)
        self.days_back = days_back
        self.max_visits = max_visits

        if history_path is None:
            base = Path(os.getenv("LOCALAPPDATA", ""))
            history_path = (
                base
                / "Google"
                / "Chrome"
                / "User Data"
                / "Default"
                / "History"
            )
        self.history_path = Path(history_path)
        self._visits: list[dict] = []
        self._loaded = False

    def load_history(self) -> None:
        """Load Chrome history into memory."""
        if self._loaded:
            return
        if not self.history_path.exists():
            self._loaded = True
            return

        temp_path = self.history_path.with_suffix(".tmp_copy.db")
        try:
            import shutil
            shutil.copy2(self.history_path, temp_path)

            cutoff = time.time() - (self.days_back * 86400)
            conn = sqlite3.connect(str(temp_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    u.url,
                    u.title,
                    v.visit_time,
                    v.transition
                FROM visits v
                JOIN urls u ON v.url = u.id
                WHERE v.visit_time > ?
                ORDER BY v.visit_time DESC
                LIMIT ?
                """,
                (cutoff, self.max_visits),
            )
            rows = cursor.fetchall()
            conn.close()

            self._visits = []
            for url, title, visit_time, transition in rows:
                chrome_time_offset = 11644473600
                ts = (visit_time / 1_000_000) - chrome_time_offset
                self._visits.append({
                    "url": url,
                    "title": title or "",
                    "timestamp": ts,
                    "session_id": self.session_id,
                    "memory_type": "chrome",
                    "priority": self._compute_priority(url, title),
                })
            self._loaded = True
        except Exception:
            self._loaded = True
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def add(self, message: dict) -> None:
        pass

    def get_recent(self, n: int = 10) -> list[dict]:
        self.load_history()
        return sorted(
            self._visits, key=lambda x: x["timestamp"], reverse=True
        )[:n]

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        self.load_history()
        query_lower = query.lower()
        scored = []
        for visit in self._visits:
            score = 0
            url_lower = visit["url"].lower()
            title_lower = visit["title"].lower()
            if query_lower in url_lower:
                score += 2
            if query_lower in title_lower:
                score += 5
            if score > 0:
                scored.append((score, visit))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "title": visit["title"],
                "url": visit["url"],
                "timestamp": visit["timestamp"],
                "score": score,
                "memory_type": "chrome",
            }
            for score, visit in scored[:top_k]
        ]

    def clear(self) -> None:
        self._visits.clear()
        self._loaded = False

    def get_stats(self) -> dict[str, Any]:
        self.load_history()
        return {
            "type": "ChromeHistoryMemory",
            "memory_type": "Semantic (Browser)",
            "visit_count": len(self._visits),
            "days_back": self.days_back,
            "max_visits": self.max_visits,
            "history_path": str(self.history_path),
            "session_id": self.session_id,
        }

    def _compute_priority(self, url: str, title: str) -> int:
        base = 1
        high_value = ["github", "stackoverflow", "docs.", "api"]
        if any(domain in url.lower() for domain in high_value):
            base += 2
        return base
