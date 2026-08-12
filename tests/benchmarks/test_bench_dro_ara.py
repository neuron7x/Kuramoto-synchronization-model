# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Micro-benchmarks for ``core.dro_ara.geosync_observe``.

Windows ∈ {256, 512, 1024}; length fixed at ``window + step`` with ``step = 64``.
Each window is measured over 5 iterations (plus one warmup); we report p50 and
p95 wall-clock and persist a deterministic artifact at
``results/dro_ara_bench.json`` with a canonical replay hash.

The artifact is intentionally emitted by a module-level session finalizer so
that exactly one JSON file is written per pytest session, regardless of test
selection order.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest
from numpy.typing import NDArray

from core.dro_ara import geosync_observe

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_RESULTS_PATH: Path = _REPO_ROOT / "results" / "dro_ara_bench.json"
_STEP: int = 64
_SEED: int = 42
_REPEATS: int = 10
_WARMUP: int = 2

_records: dict[int, dict[str, float]] = {}


def _ou_prices(n: int, seed: int = _SEED) -> NDArray[np.float64]:
    """Seeded Ornstein-Uhlenbeck-like mean-reverting price path.

    Used as a deterministic input across all benchmark variants so that
    results are reproducible bit-for-bit under a fixed NumPy version.
    """
    rng = np.random.default_rng(seed)
    theta: float = 0.05
    mu: float = 100.0
    sigma: float = 0.5
    x: NDArray[np.float64] = np.empty(n, dtype=np.float64)
    x[0] = mu
    for i in range(1, n):
        x[i] = x[i - 1] + theta * (mu - x[i - 1]) + sigma * rng.normal()
    return x


def _measure(callable_: Callable[[], Any], repeats: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        callable_()
    timings: list[float] = []
    for _ in range(repeats):
        t0: float = time.perf_counter()
        callable_()
        timings.append(time.perf_counter() - t0)
    return timings


def _percentile(timings: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(timings, dtype=np.float64), q))


def _write_artifact() -> None:
    """Persist the benchmark artifact exactly once per session.

    Skips writing when no window was exercised (e.g. when the suite was
    deselected) so we never clobber an existing artifact with an empty run.
    """
    if not _records:
        return

    payload: dict[str, Any] = {
        "schema": "dro_ara_bench.v1",
        "seed": _SEED,
        "step": _STEP,
        "repeats": _REPEATS,
        "warmup": _WARMUP,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "windows": {
            str(w): {
                "length": w + _STEP,
                "p50_sec": round(rec["p50_sec"], 9),
                "p95_sec": round(rec["p95_sec"], 9),
                "mean_sec": round(rec["mean_sec"], 9),
                "min_sec": round(rec["min_sec"], 9),
                "max_sec": round(rec["max_sec"], 9),
            }
            for w, rec in sorted(_records.items())
        },
    }
    canonical: bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    payload["replay_hash"] = hashlib.sha256(canonical).hexdigest()

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESULTS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


atexit.register(_write_artifact)


@pytest.mark.parametrize("window", [256, 512, 1024])
def test_bench_geosync_observe(window: int) -> None:
    """Benchmark ``geosync_observe`` at a fixed window size.

    The test is deterministic: inputs are seeded, repeats are bounded, and the
    assertion budget is loose enough to survive shared CI runners while still
    catching catastrophic regressions (≥10× baseline).
    """
    prices: NDArray[np.float64] = _ou_prices(window + _STEP)

    def _run() -> dict[str, Any]:
        return geosync_observe(prices, window=window, step=_STEP)

    # Warmup to stabilise caches / JIT-style effects in NumPy routines.
    timings: list[float] = _measure(_run, repeats=_REPEATS, warmup=_WARMUP)

    p50: float = _percentile(timings, 50.0)
    p95: float = _percentile(timings, 95.0)
    _records[window] = {
        "p50_sec": p50,
        "p95_sec": p95,
        "mean_sec": float(np.mean(timings)),
        "min_sec": float(np.min(timings)),
        "max_sec": float(np.max(timings)),
    }

    # Generous ceiling: single observe call on ≤1088 samples is an O(N·log N)
    # NumPy workload dominated by a handful of linear solves. A second per call
    # would indicate a catastrophic regression, not a noisy runner.
    assert p50 < 1.0, f"p50 {p50:.4f}s exceeds 1s ceiling at window={window}"
    assert p95 < 2.0, f"p95 {p95:.4f}s exceeds 2s ceiling at window={window}"
