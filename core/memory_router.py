import re
from typing import Any

from memory_backends import BaseMemory

from .memory_manager import MemoryManager


class MemoryRouter:
    """Routes queries to appropriate memory backends based on intent classification.

    Intent Categories:
    - PREFERENCES: User preferences, settings, habits (buffer > episodic > redis)
    - FACTUALITY: Factual queries, definitions, technical specs (episodic > redis)
    - EXPERIENCE: Past experiences, how-to from history (episodic > chrome > redis)
    - NAVIGATION: Browser history, URLs, pages visited (chrome > buffer)
    - GENERAL: General conversation (buffer only)
    """

    INTENT_PATTERNS = {
        "PREFERENCES": [
            r"\b(my |your )?(prefer|like|hate|favorite|always|usually)\b",
            r"\b(remember|forget|recall)\b.*\b(prefer|like|setting)\b",
            r"\bI told you\b",
        ],
        "FACTUALITY": [
            r"\b(what is|what are|define|explain)\b",
            r"\b(how do|how does|why do|why does)\b",
            r"\b(syntax|function|method|class|api)\b",
            r"\b(reference|documentation|spec)\b",
        ],
        "EXPERIENCE": [
            r"\b(we|I)( |')(ve|had|did)\b.*\b(when|before|past)\b",
            r"\b(remember|recall|earlier|before)\b",
            r"\b(from yesterday|last week|before this)\b",
            r"\b(how did we|how was)\b",
        ],
        "NAVIGATION": [
            r"\b(visit|page|site|website| browsed?|surf)\b",
            r"\b(google|search|lookup)\b",
            r"\b(url|link|address)\b",
            r"\b(from the web|online)\b",
            r"\bgithub\b",
        ],
    }

    BACKEND_PRIORITY = {
        "PREFERENCES": ["buffer", "episodic", "redis"],
        "FACTUALITY": ["episodic", "redis", "buffer"],
        "EXPERIENCE": ["episodic", "chrome", "redis"],
        "NAVIGATION": ["chrome", "buffer"],
        "GENERAL": ["buffer"],
    }

    def __init__(self, memory_manager: MemoryManager):
        self.manager = memory_manager

    def route(self, query: str) -> dict[str, Any]:
        """Classify query intent and route to appropriate memory backends."""
        intent = self._classify_intent(query)
        priority_backends = self.BACKEND_PRIORITY.get(intent, ["buffer"])

        results = {}
        for backend_name in priority_backends:
            backend: BaseMemory = self.manager._backends[backend_name]
            results[backend_name] = backend.search(query, top_k=3)

        return {
            "intent": intent,
            "query": query,
            "results": results,
            "primary_backend": priority_backends[0],
        }

    def _classify_intent(self, query: str) -> str:
        """Classify the query into one of the intent categories."""
        query_lower = query.lower()
        scores: dict[str, int] = {intent: 0 for intent in self.INTENT_PATTERNS}

        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    scores[intent] += 1

        best_intent = max(scores, key=scores.get)
        if scores[best_intent] == 0:
            return "GENERAL"
        return best_intent

    def get_context_for_query(self, query: str) -> list[dict]:
        """Retrieve relevant context for a given query from routed backends."""
        routing = self.route(query)
        context = []

        for backend_name in routing["results"]:
            backend_results = routing["results"][backend_name]
            for result in backend_results:
                content = result.get("content", "") or result.get("summary", "")
                if content:
                    context.append({
                        "role": "system",
                        "content": f"[{backend_name}] {content}",
                        "source": backend_name,
                    })

        return context
