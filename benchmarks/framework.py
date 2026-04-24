import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from memory_backends import (
    ChromeHistoryMemory,
    ConversationBufferMemory,
    JSONEpisodicMemory,
    RedisMemory,
)

from core import MemoryManager, MemoryRouter


@dataclass
class ConversationTurn:
    role: str
    content: str
    expected_intent: str = "GENERAL"


@dataclass
class TestConversation:
    name: str
    turns: list[ConversationTurn]
    description: str = ""


CONVERSATIONS = [
    TestConversation(
        name="Code Debug Session",
        description="Multi-turn debugging conversation",
        turns=[
            ConversationTurn("user", "I'm getting a TypeError in my Python code", "FACTUALITY"),
            ConversationTurn("assistant", "Please share the error message and relevant code."),
            ConversationTurn("user", "Here's the stack trace...", "FACTUALITY"),
            ConversationTurn("assistant", "The error occurs because you're passing a string where an int is expected."),
            ConversationTurn("user", "Can you explain the difference between list and tuple?", "FACTUALITY"),
        ],
    ),
    TestConversation(
        name="Project Setup",
        description="Setting up a new project",
        turns=[
            ConversationTurn("user", "I prefer using dark mode in my editor", "PREFERENCES"),
            ConversationTurn("assistant", "Got it, I'll keep that in mind."),
            ConversationTurn("user", "Create a new React project", "EXPERIENCE"),
            ConversationTurn("assistant", "I'll create a new React project with TypeScript."),
            ConversationTurn("user", "I prefer using yarn over npm", "PREFERENCES"),
        ],
    ),
    TestConversation(
        name="Browser History Query",
        description="Asking about past browsing activity",
        turns=[
            ConversationTurn("user", "What websites did I visit about machine learning?", "NAVIGATION"),
            ConversationTurn("assistant", "Based on your Chrome history, you visited several ML-related sites."),
            ConversationTurn("user", "Show me my recent GitHub repositories", "NAVIGATION"),
        ],
    ),
    TestConversation(
        name="Code Review",
        description="Multi-turn code review",
        turns=[
            ConversationTurn("user", "Review this function for best practices", "FACTUALITY"),
            ConversationTurn("assistant", "I'll review the code for performance and style issues."),
            ConversationTurn("user", "Can you refactor it to use async/await?", "FACTUALITY"),
            ConversationTurn("assistant", "I'll refactor the function to use async/await."),
            ConversationTurn("user", "I prefer having error handling with try-catch", "PREFERENCES"),
            ConversationTurn("assistant", "I'll add proper error handling."),
        ],
    ),
    TestConversation(
        name="API Integration",
        description="Integrating with external APIs",
        turns=[
            ConversationTurn("user", "How do I call a REST API in Python?", "FACTUALITY"),
            ConversationTurn("assistant", "You can use the requests library to call REST APIs."),
            ConversationTurn("user", "I need to handle authentication with JWT tokens", "FACTUALITY"),
            ConversationTurn("assistant", "I'll add JWT authentication to the API calls."),
            ConversationTurn("user", "Remember I prefer using environment variables for secrets", "PREFERENCES"),
            ConversationTurn("user", "What's my preference for API error handling?", "PREFERENCES"),
        ],
    ),
    TestConversation(
        name="Database Design",
        description="Designing a database schema",
        turns=[
            ConversationTurn("user", "Design a database schema for an e-commerce app", "FACTUALITY"),
            ConversationTurn("assistant", "I'll create tables for users, products, orders, and reviews."),
            ConversationTurn("user", "Add support for multiple addresses per user", "EXPERIENCE"),
            ConversationTurn("assistant", "I'll add an addresses table linked to users."),
            ConversationTurn("user", "I usually prefer PostgreSQL for production", "PREFERENCES"),
        ],
    ),
    TestConversation(
        name="Learning New Topic",
        description="Learning about a new concept",
        turns=[
            ConversationTurn("user", "Explain what Docker containers are", "FACTUALITY"),
            ConversationTurn("assistant", "Docker containers package your application with all its dependencies."),
            ConversationTurn("user", "How do I create a Dockerfile?", "FACTUALITY"),
            ConversationTurn("user", "I prefer using docker-compose for multi-container setups", "PREFERENCES"),
            ConversationTurn("assistant", "I'll create a docker-compose.yml for your project."),
        ],
    ),
    TestConversation(
        name="Bug Investigation",
        description="Investigating a production bug",
        turns=[
            ConversationTurn("user", "Our API is returning 500 errors", "FACTUALITY"),
            ConversationTurn("assistant", "Let me investigate the server logs."),
            ConversationTurn("user", "The error started after the last deployment", "EXPERIENCE"),
            ConversationTurn("assistant", "I'll compare the recent changes."),
            ConversationTurn("user", "Roll back to the previous version", "EXPERIENCE"),
            ConversationTurn("user", "I prefer automatic rollbacks on 5xx errors", "PREFERENCES"),
        ],
    ),
    TestConversation(
        name="Configuration Management",
        description="Managing application configuration",
        turns=[
            ConversationTurn("user", "I need to configure logging for my app", "FACTUALITY"),
            ConversationTurn("assistant", "I'll set up structured logging with rotation."),
            ConversationTurn("user", "I prefer JSON logs in production", "PREFERENCES"),
            ConversationTurn("user", "Also configure environment-specific settings", "FACTUALITY"),
            ConversationTurn("assistant", "I'll create separate config files for dev/staging/prod."),
            ConversationTurn("user", "What's my log format preference?", "PREFERENCES"),
        ],
    ),
    TestConversation(
        name="Testing Strategy",
        description="Discussing testing approach",
        turns=[
            ConversationTurn("user", "What testing framework should I use for Python?", "FACTUALITY"),
            ConversationTurn("assistant", "I recommend pytest for Python testing."),
            ConversationTurn("user", "I prefer having 80% code coverage", "PREFERENCES"),
            ConversationTurn("assistant", "I'll set up pytest with coverage reporting."),
            ConversationTurn("user", "Add integration tests for the API endpoints", "EXPERIENCE"),
            ConversationTurn("user", "What's my coverage target?", "PREFERENCES"),
        ],
    ),
]


@dataclass
class BenchmarkResult:
    conversation_name: str
    total_turns: int
    total_tokens: int
    backend_stats: dict[str, Any]
    router_intents: list[str]
    context_window_size: int
    duration_ms: float
    memory_operations: int = 0


class BenchmarkRunner:
    """Benchmark framework for evaluating memory system across multi-turn conversations."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.results: list[BenchmarkResult] = []

    def run_all(self) -> list[BenchmarkResult]:
        """Run all 10 benchmark conversations."""
        self.results = []
        for conv in CONVERSATIONS:
            result = self._run_conversation(conv)
            self.results.append(result)
        return self.results

    def _run_conversation(self, conversation: TestConversation) -> BenchmarkResult:
        session_id = f"bench_{uuid.uuid4().hex[:8]}"
        manager = MemoryManager(session_id)
        router = MemoryRouter(manager)

        start_time = time.time()
        ops = 0

        for turn in conversation.turns:
            manager.add_message(turn.role, turn.content)
            ops += 1

            routing = router.route(turn.content)
            ops += 1

            if turn.role == "assistant":
                manager.end_turn()

        context = manager.get_context()
        ops += 1

        duration_ms = (time.time() - start_time) * 1000

        return BenchmarkResult(
            conversation_name=conversation.name,
            total_turns=len(conversation.turns),
            total_tokens=sum(len(m["content"]) // 4 for m in context),
            backend_stats=manager.get_all_stats(),
            router_intents=[
                router._classify_intent(t.content) for t in conversation.turns
            ],
            context_window_size=len(context),
            duration_ms=duration_ms,
            memory_operations=ops,
        )

    def save_results(self, filename: str = "benchmark_results.json") -> None:
        """Save benchmark results to JSON file."""
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, filename)

        data = []
        for r in self.results:
            data.append({
                "conversation_name": r.conversation_name,
                "total_turns": r.total_turns,
                "total_tokens": r.total_tokens,
                "backend_stats": r.backend_stats,
                "router_intents": r.router_intents,
                "context_window_size": r.context_window_size,
                "duration_ms": round(r.duration_ms, 2),
                "memory_operations": r.memory_operations,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Results saved to {output_path}")
