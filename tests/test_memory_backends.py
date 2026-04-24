import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_backends import (
    BaseMemory,
    ChromeHistoryMemory,
    ConversationBufferMemory,
    JSONEpisodicMemory,
    RedisMemory,
)
from core import MemoryManager, MemoryRouter
from benchmarks import BenchmarkRunner, generate_report


def test_base_memory_interface():
    """Verify all backends implement BaseMemory correctly."""
    session_id = f"test_{uuid.uuid4().hex[:8]}"
    backends: list[BaseMemory] = [
        ConversationBufferMemory(session_id),
        JSONEpisodicMemory(session_id),
        RedisMemory(session_id),
        ChromeHistoryMemory(session_id),
    ]

    for backend in backends:
        assert isinstance(backend, BaseMemory)
        assert hasattr(backend, "add")
        assert hasattr(backend, "get_recent")
        assert hasattr(backend, "search")
        assert hasattr(backend, "clear")
        assert hasattr(backend, "get_stats")
    print("[PASS] All backends implement BaseMemory")


def test_buffer_memory():
    """Test ConversationBufferMemory operations."""
    session_id = f"test_buffer_{uuid.uuid4().hex[:8]}"
    mem = ConversationBufferMemory(session_id, max_messages=5)

    for i in range(7):
        mem.add({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Message {i}",
            "timestamp": time.time(),
        })

    assert len(mem.get_recent(3)) == 3
    recent = mem.get_recent(10)
    assert len(recent) == 5

    results = mem.search("Message 6", top_k=5)
    assert len(results) <= 5

    stats = mem.get_stats()
    assert stats["type"] == "ConversationBufferMemory"
    assert stats["message_count"] == 5
    print("[PASS] ConversationBufferMemory works correctly")


def test_episodic_memory():
    """Test JSONEpisodicMemory operations."""
    session_id = f"test_episodic_{uuid.uuid4().hex[:8]}"
    mem = JSONEpisodicMemory(session_id)

    for i in range(3):
        mem.add({
            "role": "user",
            "content": f"User message {i}",
            "timestamp": time.time(),
        })
        mem.add({
            "role": "assistant",
            "content": f"Assistant response {i}",
            "timestamp": time.time(),
        })
        mem.end_episode(mood="productive")

    episodes = mem.get_recent(2)
    assert len(episodes) == 2
    stats = mem.get_stats()
    assert stats["total_episodes"] == 3
    print("[PASS] JSONEpisodicMemory works correctly")


def test_redis_memory():
    """Test RedisMemory operations (graceful degradation when Redis unavailable)."""
    session_id = f"test_redis_{uuid.uuid4().hex[:8]}"
    mem = RedisMemory(session_id, host="localhost", port=6379)

    mem.add({
        "role": "user",
        "content": "Test message",
        "timestamp": time.time(),
    })

    stats = mem.get_stats()
    assert stats["type"] == "RedisMemory"
    assert "connected" in stats
    print(f"[PASS] RedisMemory (connected={stats['connected']})")


def test_chrome_memory():
    """Test ChromeHistoryMemory."""
    session_id = f"test_chrome_{uuid.uuid4().hex[:8]}"
    mem = ChromeHistoryMemory(session_id)

    results = mem.search("github", top_k=3)
    assert isinstance(results, list)
    stats = mem.get_stats()
    assert stats["type"] == "ChromeHistoryMemory"
    print("[PASS] ChromeHistoryMemory works correctly")


def test_memory_manager():
    """Test unified MemoryManager."""
    session_id = f"test_manager_{uuid.uuid4().hex[:8]}"
    manager = MemoryManager(session_id, max_total_tokens=1000)

    manager.add_message("user", "Hello, how are you?")
    manager.add_message("assistant", "I'm doing great, thanks!")

    context = manager.get_context()
    assert len(context) > 0

    stats = manager.get_all_stats()
    assert "buffer" in stats
    assert "episodic" in stats
    assert "redis" in stats
    assert "chrome" in stats
    print("[PASS] MemoryManager works correctly")


def test_memory_router():
    """Test intent-based memory router."""
    session_id = f"test_router_{uuid.uuid4().hex[:8]}"
    manager = MemoryManager(session_id)
    router = MemoryRouter(manager)

    test_cases = [
        ("I prefer using dark mode", "PREFERENCES"),
        ("What is a Python decorator?", "FACTUALITY"),
        ("Remember when we discussed APIs?", "EXPERIENCE"),
        ("Show me my GitHub history", "NAVIGATION"),
        ("Hello there!", "GENERAL"),
    ]

    for query, expected_intent in test_cases:
        routing = router.route(query)
        print(f"  Query: '{query}' -> {routing['intent']} (expected: {expected_intent})")
        assert routing["intent"] == expected_intent

    print("[PASS] MemoryRouter intent classification works correctly")


def test_benchmark_framework():
    """Run a quick benchmark with 2 conversations."""
    runner = BenchmarkRunner(output_dir="outputs")
    results = runner.run_all()

    assert len(results) == 10
    for r in results:
        assert r.total_turns > 0
        assert r.duration_ms >= 0

    runner.save_results("test_results.json")
    print("[PASS] Benchmark framework runs all 10 conversations")


def test_report_generation():
    """Test report generation."""
    runner = BenchmarkRunner(output_dir="outputs")
    runner.run_all()
    runner.save_results()

    report = generate_report(
        [
            {
                "conversation_name": r.conversation_name,
                "total_turns": r.total_turns,
                "total_tokens": r.total_tokens,
                "backend_stats": r.backend_stats,
                "router_intents": r.router_intents,
                "context_window_size": r.context_window_size,
                "duration_ms": r.duration_ms,
                "memory_operations": r.memory_operations,
            }
            for r in runner.results
        ],
        output_dir="outputs",
        format="markdown",
    )
    assert "Memory System Benchmark Report" in report
    print("[PASS] Report generation works correctly")


def run_all_tests():
    print("=" * 60)
    print("Running Memory Backend Tests")
    print("=" * 60)
    test_base_memory_interface()
    test_buffer_memory()
    test_episodic_memory()
    test_redis_memory()
    test_chrome_memory()
    test_memory_manager()
    test_memory_router()
    test_benchmark_framework()
    test_report_generation()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
