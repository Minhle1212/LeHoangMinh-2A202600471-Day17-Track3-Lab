from typing import TypedDict, NotRequired
from typing_extensions import Annotated
import operator


class MemoryState(TypedDict, total=False):
    """LangGraph state for the multi-memory agent.

    All memory types are explicitly separated so the router can
    inject each section into the system prompt cleanly.
    """

    messages: Annotated[list[dict], operator.add]

    # --- Memory fields ---
    user_profile: dict
    episodes: list[dict]
    semantic_hits: list[str]
    recent_messages: list[dict]

    # --- Budget / control ---
    memory_budget: int
    total_tokens: int

    # --- Routing metadata ---
    current_intent: str
    primary_memory_backend: str

    # --- Reflection ---
    reflection_notes: list[str]
    privacy_flags: list[str]

    # --- Output ---
    response: str
    memory_operation: str
