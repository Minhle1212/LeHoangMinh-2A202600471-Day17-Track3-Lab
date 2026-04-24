#!/usr/bin/env python3
"""Main entry point for the Multi-Agent Memory System."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmarks import BenchmarkRunner, generate_report


def main():
    print("  Multi-Agent Memory System - Benchmark Runner")
    

    runner = BenchmarkRunner(output_dir="outputs")
    print("Running benchmarks for 10 multi-turn conversations...")
    results = runner.run_all()

    print(f"\nCompleted {len(results)} conversations.\n")

    runner.save_results("benchmark_results.json")

    report_data = [
        {
            "conversation_name": r.conversation_name,
            "total_turns": r.total_turns,
            "total_tokens": r.total_tokens,
            "backend_stats": r.backend_stats,
            "router_intents": r.router_intents,
            "context_window_size": r.context_window_size,
            "duration_ms": round(r.duration_ms, 2),
            "memory_operations": r.memory_operations,
        }
        for r in results
    ]
    generate_report(report_data, output_dir="outputs", format="markdown")

    print("  Benchmark Complete!")
    print("\nOutputs saved to 'outputs/' directory:")
    print("  - benchmark_results.json   (raw data)")
    print("  - benchmark_report.md      (markdown report)")


if __name__ == "__main__":
    main()
