from typing import Any

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None
    MemorySaver = None

from .state import MemoryState
from .nodes import (
    retrieve_memory_node,
    update_memory_node,
    trim_memory_node,
    reflect_on_memory_node,
)


def build_memory_agent_graph() -> Any:
    """Build the LangGraph workflow for the multi-memory agent.

    Graph flow:
        retrieve_memory
              ↓
        update_memory
              ↓
        trim_memory
              ↓
        reflect_on_memory → END

    Each node receives the full MemoryState and returns partial updates.
    """
    if not LANGGRAPH_AVAILABLE:
        return None

    builder = StateGraph(MemoryState)

    builder.add_node("retrieve_memory", retrieve_memory_node)
    builder.add_node("update_memory", update_memory_node)
    builder.add_node("trim_memory", trim_memory_node)
    builder.add_node("reflect_on_memory", reflect_on_memory_node)

    builder.set_entry_point("retrieve_memory")
    builder.add_edge("retrieve_memory", "update_memory")
    builder.add_edge("update_memory", "trim_memory")
    builder.add_edge("trim_memory", "reflect_on_memory")
    builder.add_edge("reflect_on_memory", END)

    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    return graph


def run_agent_message(
    graph,
    session_id: str,
    user_message: str,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Run a single user message through the full memory graph.

    Args:
        graph: Compiled LangGraph
        session_id: Unique session identifier
        user_message: The user's message

    Returns:
        Final MemoryState after all nodes run
    """
    from langgraph.graph import START

    initial_state: MemoryState = {
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ],
        "user_profile": {"session_id": session_id},
        "episodes": [],
        "semantic_hits": [],
        "recent_messages": [],
        "memory_budget": 4000,
        "total_tokens": 0,
        "current_intent": "GENERAL",
        "primary_memory_backend": "buffer",
        "reflection_notes": [],
        "privacy_flags": [],
        "response": "",
        "memory_operation": "",
    }

    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
    return result


def format_system_prompt(state: MemoryState) -> str:
    """Format the system prompt by injecting all memory sections cleanly.

    Sections:
    1. Base instructions
    2. User profile (long-term)
    3. Recent conversation (short-term)
    4. Episodic memories
    5. Semantic hits (Chrome/Redis)
    6. Reflection notes
    """
    sections = []

    sections.append("You are a helpful AI assistant.")

    profile = state.get("user_profile", {})
    if profile:
        facts = [f"  - {k}: {v}" for k, v in profile.items() if k != "session_id"]
        if facts:
            sections.append("\n## User Profile (learned facts)")
            sections.extend(facts)

    recent = state.get("recent_messages", [])
    if recent:
        sections.append("\n## Recent Conversation")
        for msg in recent[-5:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            sections.append(f"[{role}] {content}")

    episodes = state.get("episodes", [])
    if episodes:
        sections.append("\n## Episodic Memories (past experiences)")
        for ep in episodes[:3]:
            summary = ep.get("summary", "")
            if summary:
                sections.append(f"  - {summary}")

    semantic = state.get("semantic_hits", [])
    if semantic:
        sections.append("\n## Semantic Context (from browsing/web)")
        for hit in semantic[:3]:
            sections.append(f"  - {hit}")

    reflection = state.get("reflection_notes", [])
    if reflection:
        sections.append("\n## Memory System Notes")
        for note in reflection:
            sections.append(f"  - {note}")

    return "\n".join(sections)
