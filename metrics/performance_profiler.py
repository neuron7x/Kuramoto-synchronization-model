from __future__ import annotations

import statistics
import time
import tracemalloc
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RuntimeCost:
    mean_ms: float
    stdev_ms: float
    variance_pct: float
    overhead_pct: float
    peak_memory_kib: float


def profile_validation_cycle(
    validation_fn: Callable[[], None],
    baseline_fn: Callable[[], None],
    runs: int = 20,
) -> RuntimeCost:
    v_times: list[float] = []
    b_times: list[float] = []
    tracemalloc.start()
    try:
        for _ in range(runs):
            t0 = time.perf_counter()
            baseline_fn()
            b_times.append((time.perf_counter() - t0) * 1000)

            t1 = time.perf_counter()
            validation_fn()
            v_times.append((time.perf_counter() - t1) * 1000)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    v_mean = statistics.mean(v_times)
    v_stdev = statistics.pstdev(v_times)
    b_mean = max(statistics.mean(b_times), 1e-9)
    variance_pct = (v_stdev / max(v_mean, 1e-9)) * 100
    return RuntimeCost(
        mean_ms=v_mean,
        stdev_ms=v_stdev,
        variance_pct=variance_pct,
        overhead_pct=((v_mean - b_mean) / b_mean) * 100,
        peak_memory_kib=peak / 1024.0,
    )
