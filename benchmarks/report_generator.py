import os
import json
from datetime import datetime
from typing import Any

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def generate_report(
    results: list[dict],
    output_dir: str = "outputs",
    format: str = "markdown",
) -> str:
    """Generate a performance report from benchmark results.

    Args:
        results: List of benchmark result dicts from BenchmarkRunner
        output_dir: Directory to save report files
        format: Output format - 'markdown', 'html', or 'json'

    Returns:
        Report content as a string
    """
    os.makedirs(output_dir, exist_ok=True)

    if format == "json":
        report_path = os.path.join(output_dir, "benchmark_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return report_path

    report_lines = [
        "# Memory System Benchmark Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n**Total Conversations:** {len(results)}",
        "",
    ]

    total_turns = sum(r["total_turns"] for r in results)
    avg_duration = sum(r["duration_ms"] for r in results) / len(results)
    total_ops = sum(r["memory_operations"] for r in results)

    report_lines.extend([
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Conversations | {len(results)} |",
        f"| Total Turns | {total_turns} |",
        f"| Total Memory Operations | {total_ops} |",
        f"| Avg Duration per Conversation | {avg_duration:.2f} ms |",
        "",
    ])

    report_lines.extend(["## Per-Conversation Results", ""])
    for r in results:
        report_lines.append(f"### {r['conversation_name']}")
        report_lines.extend([
            f"- Turns: {r['total_turns']}",
            f"- Duration: {r['duration_ms']:.2f} ms",
            f"- Memory Operations: {r['memory_operations']}",
            f"- Context Window Size: {r['context_window_size']}",
            f"- Intents: {', '.join(r['router_intents'])}",
            "",
        ])

    intent_counts: dict[str, int] = {}
    for r in results:
        for intent in r["router_intents"]:
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

    report_lines.extend(["## Intent Distribution", ""])
    report_lines.append("| Intent | Count |")
    report_lines.append("|-------|-------|")
    for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"| {intent} | {count} |")
    report_lines.append("")

    report_lines.extend(["## Memory Backend Statistics", ""])
    buffer_avg = sum(
        r["backend_stats"].get("buffer", {}).get("message_count", 0)
        for r in results
    ) / len(results)
    episodic_total = sum(
        r["backend_stats"].get("episodic", {}).get("total_episodes", 0)
        for r in results
    )

    report_lines.extend([
        "| Backend | Avg Count |",
        "|---------|-----------|",
        f"| ConversationBuffer | {buffer_avg:.1f} messages |",
        f"| JSONEpisodic | {episodic_total} episodes |",
        "",
    ])

    report_text = "\n".join(report_lines)

    if format == "markdown":
        report_path = os.path.join(output_dir, "benchmark_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"Report saved to {report_path}")

    if PLOTLY_AVAILABLE and format == "markdown":
        pass  # Charts disabled

    return report_text


def _generate_charts(results: list[dict], output_dir: str) -> None:
    """Generate performance charts from results."""
    names = [r["conversation_name"] for r in results]
    durations = [r["duration_ms"] for r in results]
    turns = [r["total_turns"] for r in results]
    ops = [r["memory_operations"] for r in results]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Memory System Benchmark Results", fontsize=16, fontweight="bold")

    axes[0, 0].barh(names, durations, color="#4C78A8")
    axes[0, 0].set_xlabel("Duration (ms)")
    axes[0, 0].set_title("Duration per Conversation")

    axes[0, 1].barh(names, turns, color="#F58518")
    axes[0, 1].set_xlabel("Turns")
    axes[0, 1].set_title("Turns per Conversation")

    axes[1, 0].barh(names, ops, color="#54A24B")
    axes[1, 0].set_xlabel("Operations")
    axes[1, 0].set_title("Memory Operations per Conversation")

    context_sizes = [r["context_window_size"] for r in results]
    axes[1, 1].barh(names, context_sizes, color="#E45756")
    axes[1, 1].set_xlabel("Context Size")
    axes[1, 1].set_title("Context Window Size")

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "benchmark_charts.png")
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Charts saved to {chart_path}")
