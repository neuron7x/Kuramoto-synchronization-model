#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Benchmark dopamine module step() performance.

Target: ≥15k step/s on reference CPU.

Usage:
    python benchmarks/dopamine_step_bench.py [--profile PROFILE]

Options:
    --profile PROFILE   Use specific config profile (conservative, normal, aggressive)
    --iterations N      Number of iterations (default: 100000)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add src to path for direct import - import only the dopamine controller module
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "geosync" / "core" / "neuro"))

from dopamine.dopamine_controller import DopamineController

from utils.seed import set_global_seed


def benchmark_step(controller: DopamineController, iterations: int = 100000) -> dict[str, float]:
    """Benchmark dopamine controller step performance.

    Args:
        controller: DopamineController instance
        iterations: Number of step() calls to perform

    Returns:
        Dict with benchmark results
    """
    # Warm-up
    for _ in range(100):
        controller.step(
            reward=0.5,
            value=0.2,
            next_value=0.25,
            appetitive_state=0.3,
            policy_logits=(0.1, 0.2, 0.3),
        )

    controller.reset_state()

    # Actual benchmark
    start_time = time.perf_counter()

    for i in range(iterations):
        # Vary inputs slightly to avoid unrealistic caching
        reward = 0.5 + (i % 10) * 0.01
        value = 0.2 + (i % 5) * 0.02
        next_value = value + 0.05
        appetitive = 0.3 + (i % 7) * 0.01

        controller.step(
            reward=reward,
            value=value,
            next_value=next_value,
            appetitive_state=appetitive,
            policy_logits=(0.1, 0.2, 0.3),
        )

    end_time = time.perf_counter()
    elapsed = end_time - start_time

    steps_per_sec = iterations / elapsed
    microsec_per_step = (elapsed / iterations) * 1e6

    return {
        "iterations": iterations,
        "elapsed_sec": elapsed,
        "steps_per_sec": steps_per_sec,
        "microsec_per_step": microsec_per_step,
    }


def main() -> int:
    """Main benchmark entry point."""
    parser = argparse.ArgumentParser(description="Benchmark dopamine step performance")
    parser.add_argument(
        "--profile",
        choices=["conservative", "normal", "aggressive"],
        default="normal",
        help="Config profile to use",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100000,
        help="Number of iterations",
    )

    args = parser.parse_args()
    set_global_seed()

    # Load config
    if args.profile == "normal":
        config_path = "config/dopamine.yaml"
    else:
        config_path = f"config/profiles/{args.profile}.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    print("Dopamine Step Benchmark")
    print("=" * 60)
    print(f"Profile: {args.profile}")
    print(f"Config: {config_path}")
    print(f"Iterations: {args.iterations:,}")
    print()

    # Create controller
    controller = DopamineController(config_path=str(config_file))

    # Run benchmark
    print("Running benchmark...")
    results = benchmark_step(controller, iterations=args.iterations)

    # Display results
    print()
    print("Results:")
    print("-" * 60)
    print(f"  Total iterations: {results['iterations']:,}")
    print(f"  Elapsed time: {results['elapsed_sec']:.3f} seconds")
    print(f"  Steps per second: {results['steps_per_sec']:,.0f}")
    print(f"  Microseconds per step: {results['microsec_per_step']:.2f} μs")
    print()

    # Check against target
    target = 15000
    if results["steps_per_sec"] >= target:
        print(f"✅ PASS: Meets target of ≥{target:,} steps/s")
        return 0
    else:
        shortfall = target - results["steps_per_sec"]
        pct = (shortfall / target) * 100
        print(
            f"❌ FAIL: Below target of ≥{target:,} steps/s (short by {shortfall:,.0f} or {pct:.1f}%)"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
