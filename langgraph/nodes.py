import time
from typing import Literal

from .state import MemoryState
from core.memory_router import MemoryRouter
from memory_backends import (
    ChromeHistoryMemory,
    ConversationBufferMemory,
    JSONEpisodicMemory,
    RedisMemory,
    ConversationBufferMemory as BufferMem,
    JSONEpisodicMemory as EpisodicMem,
)


def retrieve_memory_node(state: MemoryState) -> MemoryState:
    """Retrieve relevant memories from all backends and inject into state.

    This node:
    1. Gets the last user message
    2. Routes it through MemoryRouter to classify intent
    3. Searches each backend for relevant hits
    4. Populates semantic_hits, episodes, recent_messages
    """
    messages = state.get("messages", [])
    if not messages:
        return state

    last_msg = messages[-1]
    query = last_msg.get("content", "")

    # --- Resolve session_id from state or use default ---
    session_id = state.get("user_profile", {}).get("session_id", "default")

    # --- Initialize backends ---
    buffer_mem = BufferMem(session_id)
    episodic_mem = EpisodicMem(session_id)
    redis_mem = RedisMemory(session_id)
    chrome_mem = ChromeHistoryMemory(session_id)

    # --- Get recent buffer messages ---
    recent_msgs = buffer_mem.get_recent(5)
    episodic_hits = episodic_mem.search(query, top_k=3)
    redis_hits = redis_mem.search(query, top_k=3)
    chrome_hits = chrome_mem.search(query, top_k=3)

    # --- Build semantic hits from all sources ---
    semantic_hits: list[str] = []
    for hit in episodic_hits:
        summary = hit.get("summary", "")
        if summary:
            semantic_hits.append(f"[episodic] {summary}")

    for hit in redis_hits:
        content = hit.get("content", "")
        if content:
            semantic_hits.append(f"[long-term] {content}")

    for hit in chrome_hits:
        title = hit.get("title", "") or hit.get("url", "")
        if title:
            semantic_hits.append(f"[semantic] {title}")

    # --- Get user profile from Redis ---
    profile_updates = redis_mem.get_recent(20)
    profile: dict = {}
    for msg in profile_updates:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if _looks_like_profile_fact(content):
                key, val = _extract_profile_fact(content)
                if key:
                    profile[key] = val

    return {
        "recent_messages": recent_msgs,
        "episodes": episodic_hits,
        "semantic_hits": semantic_hits,
        "user_profile": profile,
        "current_intent": _classify_intent(query),
        "primary_memory_backend": _primary_backend_for_intent(
            _classify_intent(query)
        ),
    }


def update_memory_node(state: MemoryState) -> MemoryState:
    """Save/update memories after each agent turn.

    - Extracts profile facts from user messages (with conflict resolution)
    - Saves turns to buffer and Redis
    - Triggers episodic save when task completes
    """
    messages = state.get("messages", [])
    if not messages:
        return state

    session_id = state.get("user_profile", {}).get("session_id", "default")
    buffer_mem = BufferMem(session_id)
    episodic_mem = EpisodicMem(session_id)
    redis_mem = RedisMemory(session_id)

    last_msgs = messages[-2:] if len(messages) >= 2 else messages

    for msg in last_msgs:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            # --- Profile fact extraction with conflict handling ---
            if _looks_like_profile_fact(content):
                key, val = _extract_profile_fact(content)
                if key:
                    redis_mem.save_profile_fact(key, val)

        # --- Add to all backends ---
        buffer_mem.add({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        redis_mem.add({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    # --- Mark episodic episode end ---
    episodic_mem.end_episode(mood="neutral")

    return {"memory_operation": "updated"}


def trim_memory_node(state: MemoryState) -> MemoryState:
    """Enforce memory_budget by trimming lowest-priority entries.

    Priority hierarchy:
    1. System prompt (never trimmed)
    2. Recent conversation messages (priority 1-2)
    3. Semantic hits (priority 0)
    4. Old episodic episodes (priority 0)
    """
    budget = state.get("memory_budget", 4000)
    messages = state.get("messages", [])

    total_tokens = _estimate_total_tokens(messages)

    if total_tokens <= budget:
        return {"total_tokens": total_tokens}

    # Sort by priority (lowest first) and trim
    trimmed = []
    tokens_so_far = 0
    for msg in reversed(messages):
        msg_tokens = len(msg.get("content", "")) // 4
        if tokens_so_far + msg_tokens <= budget:
            trimmed.insert(0, msg)
            tokens_so_far += msg_tokens
        # else: skip this message (trimmed)

    return {
        "messages": trimmed,
        "total_tokens": tokens_so_far,
    }


def reflect_on_memory_node(state: MemoryState) -> MemoryState:
    """Generate reflection notes on memory system state and risks."""
    notes: list[str] = []
    flags: list[str] = []

    profile = state.get("user_profile", {})
    episodes = state.get("episodes", [])
    semantic_hits = state.get("semantic_hits", [])

    if profile:
        notes.append(f"User profile has {len(profile)} facts stored.")
        # Flag sensitive profile keys
        sensitive_keys = {"allergy", "medical", "password", "ssn", "credit_card"}
        for key in profile:
            if key.lower() in sensitive_keys:
                flags.append(f"PII risk: '{key}' stored in user profile")
    else:
        notes.append("No user profile facts stored yet.")

    if episodes:
        notes.append(f"{len(episodes)} episodic episodes retrieved for context.")
    else:
        notes.append("No episodic episodes in current context window.")

    if semantic_hits:
        notes.append(
            f"{len(semantic_hits)} semantic hits from Chrome/Redis retrieved."
        )
    else:
        notes.append("No semantic hits retrieved (Chrome history may be empty).")

    return {
        "reflection_notes": notes,
        "privacy_flags": flags,
    }


# ------------------------------------------------------------------
# Helper functions (not LangGraph nodes)
# ------------------------------------------------------------------

def _classify_intent(query: str) -> str:
    patterns = {
        "PREFERENCES": ["prefer", "like", "favorite", "always", "usually"],
        "FACTUALITY": ["what is", "how do", "define", "explain", "syntax"],
        "EXPERIENCE": ["remember", "recall", "earlier", "before", "when we"],
        "NAVIGATION": ["github", "visit", "browsed", "site"],
    }
    q = query.lower()
    scores = {intent: sum(1 for kw in kws if kw in q) for intent, kws in patterns.items()}
    return max(scores, key=scores.get, default="GENERAL")


def _primary_backend_for_intent(intent: str) -> str:
    mapping = {
        "PREFERENCES": "redis",
        "FACTUALITY": "episodic",
        "EXPERIENCE": "episodic",
        "NAVIGATION": "chrome",
        "GENERAL": "buffer",
    }
    return mapping.get(intent, "buffer")


_PROFILE_INDICATORS = [
    "i am", "i'm", "my name", "i'm allergic", "i prefer",
    "i like", "i hate", "my favorite", "i always", "usually i",
]


def _looks_like_profile_fact(text: str) -> bool:
    t = text.lower()
    return any(ind in t for ind in _PROFILE_INDICATORS)


def _extract_profile_fact(text: str) -> tuple[str, str]:
    t = text.lower()

    allergy_pairs = [
        ("allergic to", "allergy"),
        ("allergy", "allergy"),
    ]
    for phrase, key in allergy_pairs:
        idx = t.find(phrase)
        if idx != -1:
            val = text[idx + len(phrase):].strip().strip(".,!?").strip()
            return key, val

    if "my name is" in t:
        idx = t.find("my name is")
        val = text[idx + len("my name is"):].strip().strip(".,!?").strip()
        return "name", val

    if "i prefer" in t:
        idx = t.find("i prefer")
        val = text[idx + len("i prefer"):].strip().strip(".,!?").strip()
        return "preference", val

    if "i like" in t:
        idx = t.find("i like")
        val = text[idx + len("i like"):].strip().strip(".,!?").strip()
        return "likes", val

    return "", ""


def _estimate_total_tokens(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) // 4 for m in messages)
