#!/usr/bin/env python
"""Run golden path performance benchmark and generate report.

This script is the canonical entrypoint for performance measurements.
It can be run directly or via `make perf-golden-path`.
"""

import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

try:
    from tradepulse.perf.golden_path import run_golden_path_bench
    from tradepulse.perf.io import format_summary, write_perf_report
except ImportError as e:
    print(f"Error: Unable to import performance modules: {e}")
    print("\nMake sure you have installed TradePulse:")
    print("  pip install -e .")
    sys.exit(1)


def main():
    """Run benchmark and save results."""
    print("=" * 60)
    print("Golden Path Performance Benchmark")
    print("=" * 60)
    print()

    # Run benchmark
    print("Running benchmark...")
    try:
        results = run_golden_path_bench(
            n_bars=252,  # 1 year of daily data
            n_iterations=100,  # 100 iterations for stable statistics
            seed=42,
        )
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        sys.exit(1)

    print("✅ Benchmark complete\n")

    # Save to JSON
    output_path = repo_root / "reports" / "perf" / "golden_path_backtest.json"
    try:
        write_perf_report(results, output_path)
        print(f"📊 Results saved to: {output_path}\n")
    except Exception as e:
        print(f"\n❌ Failed to save results: {e}")
        sys.exit(1)

    # Print summary
    summary = format_summary(results)
    print(summary)

    # Summary for CI
    latency = results["latency_ms"]
    throughput = results["throughput"]
    print("\n" + "=" * 60)
    print("Quick Summary:")
    print(f"  p50={latency['p50']:.2f}ms p95={latency['p95']:.2f}ms p99={latency['p99']:.2f}ms")
    print(f"  throughput={throughput['bars_per_second']:.0f} bars/s")
    print("=" * 60)


if __name__ == "__main__":
    main()
