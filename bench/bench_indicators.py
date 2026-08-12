# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmarks for indicator hot loops with cold/warm profiles."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable

import numpy as np

from core.indicators.entropy import entropy
from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase
from core.indicators.ricci import mean_ricci

RNG = np.random.default_rng(7)
WINDOW = 16_384


def _time_function(func: Callable[[], None], *, repeat: int) -> list[float]:
    samples: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        samples.append(time.perf_counter() - start)
    return samples


def benchmark_indicator(
    name: str,
    compute: Callable[[np.ndarray], None],
    *,
    repeat: int,
    warmup: int,
) -> None:
    cold_samples = _time_function(lambda: compute(RNG.standard_normal(WINDOW)), repeat=repeat)

    shared_data = RNG.standard_normal(WINDOW)
    for _ in range(warmup):
        compute(shared_data)
    hot_samples = _time_function(lambda: compute(shared_data), repeat=repeat)

    cold_best = min(cold_samples)
    hot_best = min(hot_samples)
    print(
        f"{name:<24s} cold_best={cold_best * 1e3:6.2f} ms  hot_best={hot_best * 1e3:6.2f} ms  "
        f"hot/ cold={hot_best / cold_best:5.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, help="number of measured iterations")
    parser.add_argument("--warmup", type=int, default=3, help="warmup runs before hot timings")
    args = parser.parse_args()

    def run_entropy(data: np.ndarray) -> None:
        entropy(data, bins=50, use_float32=True)

    def run_hurst(data: np.ndarray) -> None:
        hurst_exponent(data, use_float32=True)

    def run_phase(data: np.ndarray) -> None:
        compute_phase(data, use_float32=True)

    def run_ricci(data: np.ndarray) -> None:
        prices = data[:4_096]  # Ricci requires smaller graph for stability
        mean_ricci(prices, chunk_size=512, use_float32=True)

    benches: dict[str, Callable[[np.ndarray], None]] = {
        "entropy": run_entropy,
        "hurst_exponent": run_hurst,
        "compute_phase": run_phase,
        "mean_ricci": run_ricci,
    }

    for name, fn in benches.items():
        benchmark_indicator(name, fn, repeat=args.repeat, warmup=args.warmup)


if __name__ == "__main__":
    main()
