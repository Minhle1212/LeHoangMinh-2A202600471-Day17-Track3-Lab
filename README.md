# LeHoangMinh-2A202600471-Day17-Track3-Lab

Multi-Agent Memory System with LangGraph — Lab #17

> **Redis is optional.** If no Redis server is running, the system automatically falls back to in-memory storage. No configuration needed.

## Project Structure

```
LeHoangMinh-2A202600471-Day17-Track3-Lab/
├── memory_backends/
│   ├── base.py                  # BaseMemory abstract class
│   ├── buffer_memory.py         # ConversationBufferMemory (Short-term)
│   ├── redis_memory.py          # RedisMemory (Long-term) + profile + conflict handling
│   ├── json_episodic_memory.py  # JSONEpisodicMemory (Episodic)
│   └── chrome_memory.py         # ChromeHistoryMemory (Semantic)
├── core/
│   ├── memory_manager.py        # Unified MemoryManager with context window
│   └── memory_router.py         # Query-intent router
├── langgraph/
│   ├── state.py                 # MemoryState TypedDict
│   ├── nodes.py                # retrieve/update/trim/reflect nodes
│   └── graph.py                # build_memory_agent_graph() + prompt injection
├── benchmarks/
│   ├── framework.py             # Benchmark runner for 10 conversations
│   └── report_generator.py      # Performance report + charts
├── tests/
│   └── test_memory_backends.py
├── BENCHMARK.md                 # Full benchmark report (required submission)
├── main.py
├── requirements.txt
└── .env.example
```

## 4 Memory Backends

| Backend | Type | Storage | Use Case |
|---------|------|---------|----------|
| ConversationBufferMemory | Short-term | In-memory deque | Current session context |
| RedisMemory | Long-term | Redis (+ in-memory fallback) | Cross-session profile & facts |
| JSONEpisodicMemory | Episodic | JSON file | Event-based experience logging |
| ChromeHistoryMemory | Semantic | Chrome SQLite | Web history & learned facts |

## LangGraph Integration

MemoryState TypedDict with 4 memory fields, router node, and clean prompt injection:

```python
class MemoryState(TypedDict):
    messages: Annotated[list, operator.add]
    user_profile: dict        # from Redis
    episodes: list[dict]      # from JSONEpisodic
    semantic_hits: list[str]  # from Chrome + Redis
    recent_messages: list     # from Buffer
    memory_budget: int        # token limit
    current_intent: str       # PREFERENCES / FACTUALITY / EXPERIENCE / NAVIGATION / GENERAL
    reflection_notes: list[str]
    privacy_flags: list[str]
```

Graph flow: retrieve_memory → update_memory → trim_memory → reflect_on_memory → END

## Context Window Management

- Priority Levels: system (3) > assistant (2) > user (1) > semantic (0)
- Auto-trim when max_length exceeded
- Hierarchical eviction: oldest semantic → oldest episodic → oldest messages
- Conflict resolution: new profile facts always overwrite old facts

## Run

```bash
pip install -r requirements.txt
python main.py          # Run benchmarks
python tests/test_memory_backends.py  # Run tests
```

## Benchmark

See `BENCHMARK.md` for full report with:
- 10 multi-turn conversations (no-memory vs with-memory comparison)
- Conflict update test (rubric requirement)
- Privacy reflection & limitations analysis
- Self-assessed score: ~94/100 (+8 bonus potential)
