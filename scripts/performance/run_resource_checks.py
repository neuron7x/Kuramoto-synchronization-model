"""Collect runtime resource metrics for performance regression analysis.

This utility mirrors critical scenarios from ``tests/performance`` so the CI
pipeline can persist resource measurements (memory, CPU, response time).

The generated payload is consumed by ``compare_performance.py`` which compares
against the ``main`` branch to detect regressions.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import walk_forward  # noqa: E402 - after sys.path setup
from core.agent.strategy import Strategy  # noqa: E402
from core.data.preprocess import normalize_df, scale_series  # noqa: E402
from core.indicators.entropy import EntropyFeature  # noqa: E402
from core.indicators.hierarchical_features import (  # noqa: E402
    FeatureBufferCache,
    compute_hierarchical_features,
)
from core.indicators.hurst import HurstFeature  # noqa: E402
from core.indicators.kuramoto import (  # noqa: E402
    KuramotoOrderFeature,
    compute_phase,
    kuramoto_order,
)
from core.indicators.pipeline import IndicatorPipeline  # noqa: E402

Category = Literal["memory", "cpu", "response"]


@dataclass(slots=True)
class Metric:
    """Structured metric entry emitted by the collector."""

    name: str
    value: float
    unit: str
    category: Category
    budget: float | None = None
    details: dict[str, float | int] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "category": self.category,
        }
        if self.budget is not None:
            payload["budget"] = self.budget
        if self.details:
            payload["details"] = dict(self.details)
        return payload


def _measure_peak_bytes(func: Callable[[], Any], *, iterations: int) -> int:
    """Return the maximum resident allocation observed for ``func``."""

    tracemalloc.start()
    try:
        for _ in range(iterations):
            func()
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        gc.collect()
    return peak


def _measure_cpu_seconds(func: Callable[[], Any], *, rounds: int) -> float:
    """Average CPU seconds spent executing ``func`` over ``rounds`` iterations."""

    start = time.process_time()
    for _ in range(rounds):
        func()
    cpu_seconds = time.process_time() - start
    return cpu_seconds / max(1, rounds)


def _measure_response_seconds(func: Callable[[], Any], *, rounds: int = 1) -> float:
    """Average wall-clock duration for ``func``."""

    elapsed = 0.0
    for _ in range(rounds):
        start = time.perf_counter()
        func()
        elapsed += time.perf_counter() - start
    return elapsed / max(1, rounds)


def _compute_phase_peak_memory() -> Metric:
    samples = np.random.default_rng(7).normal(size=262_144).astype(np.float32)

    def _run() -> None:
        compute_phase(samples, use_float32=True)

    peak = _measure_peak_bytes(_run, iterations=5)
    return Metric(
        name="kuramoto.compute_phase.peak_memory",
        value=float(peak),
        unit="bytes",
        category="memory",
        budget=float(50 * 1024 * 1024),
        details={"iterations": 5, "sample_size": int(samples.size)},
    )


def _indicator_pipeline_peak_memory() -> Metric:
    rng = np.random.default_rng(21)
    data = rng.normal(size=131_072).astype(np.float32)
    pipeline = IndicatorPipeline(
        [
            EntropyFeature(name="entropy", bins=64, use_float32=True),
            HurstFeature(name="hurst", use_float32=True),
            KuramotoOrderFeature(name="kuramoto", use_float32=True),
        ]
    )

    def _run() -> None:
        result = pipeline.run(data)
        result.release()

    peak = _measure_peak_bytes(_run, iterations=6)
    return Metric(
        name="indicator.pipeline.peak_memory",
        value=float(peak),
        unit="bytes",
        category="memory",
        budget=float(64 * 1024 * 1024),
        details={"iterations": 6, "sample_size": int(data.size)},
    )


def _hierarchical_features_peak_memory() -> Metric:
    rows = 4_096
    index = pd.date_range("2024-01-01", periods=rows, freq="min")
    rng = np.random.default_rng(2024)
    base = rng.normal(scale=0.2, size=rows).cumsum() + 100.0
    frame = pd.DataFrame(
        {
            "open": base,
            "high": base + rng.normal(scale=0.1, size=rows),
            "low": base - rng.normal(scale=0.1, size=rows),
            "close": base + rng.normal(scale=0.05, size=rows),
            "volume": rng.lognormal(mean=2.0, sigma=0.3, size=rows),
        },
        index=index,
    )
    ohlcv = {
        "1m": frame,
        "5m": frame.resample("5min").last().ffill(),
        "15m": frame.resample("15min").last().ffill(),
    }

    def _run() -> None:
        cache = FeatureBufferCache()
        compute_hierarchical_features(ohlcv, cache=cache)

    peak = _measure_peak_bytes(_run, iterations=4)
    return Metric(
        name="hierarchical.features.peak_memory",
        value=float(peak),
        unit="bytes",
        category="memory",
        budget=float(80 * 1024 * 1024),
        details={"iterations": 4, "rows": rows},
    )


def _compute_phase_cpu_time() -> Metric:
    samples = (
        np.random.default_rng(1337).normal(scale=1.0, size=131_072).astype(np.float32)
    )

    cpu_seconds = _measure_cpu_seconds(
        lambda: compute_phase(samples, use_float32=True), rounds=10
    )
    return Metric(
        name="kuramoto.compute_phase.cpu_seconds",
        value=float(cpu_seconds),
        unit="seconds",
        category="cpu",
        details={"rounds": 10, "sample_size": int(samples.size)},
    )


def _kuramoto_order_cpu_time() -> Metric:
    phases = (
        np.random.default_rng(31415)
        .uniform(-np.pi, np.pi, size=(4_096, 12))
        .astype(np.float32)
    )

    cpu_seconds = _measure_cpu_seconds(lambda: kuramoto_order(phases), rounds=12)
    return Metric(
        name="kuramoto.order.cpu_seconds",
        value=float(cpu_seconds),
        unit="seconds",
        category="cpu",
        details={"rounds": 12, "matrix_shape": f"{phases.shape[0]}x{phases.shape[1]}"},
    )


def _walk_forward_response_time() -> Metric:
    prices = np.linspace(100.0, 150.0, 10_000)
    noise = np.random.default_rng(42).normal(scale=5.0, size=10_000)
    prices = prices + noise

    def simple_signal(p: np.ndarray) -> np.ndarray:
        short_ma = np.convolve(p, np.ones(20) / 20, mode="same")
        long_ma = np.convolve(p, np.ones(50) / 50, mode="same")
        return np.where(short_ma > long_ma, 1.0, -1.0)

    duration = _measure_response_seconds(
        lambda: walk_forward(prices, simple_signal, fee=0.001), rounds=1
    )
    return Metric(
        name="backtest.walk_forward.response_seconds",
        value=float(duration),
        unit="seconds",
        category="response",
        budget=5.0,
        details={"dataset_size": int(prices.size)},
    )


def _strategy_response_time() -> Metric:
    prices = 100.0 + np.cumsum(
        np.random.default_rng(123).normal(scale=0.1, size=50_000)
    )
    frame = pd.DataFrame({"close": prices})
    strategy = Strategy(name="large", params={"lookback": 50, "threshold": 0.5})

    duration = _measure_response_seconds(
        lambda: strategy.simulate_performance(frame), rounds=1
    )
    return Metric(
        name="strategy.simulate_performance.response_seconds",
        value=float(duration),
        unit="seconds",
        category="response",
        budget=10.0,
        details={"rows": int(frame.shape[0])},
    )


def _scale_series_response_time() -> Metric:
    data = np.random.default_rng(2025).normal(size=100_000)
    duration = _measure_response_seconds(
        lambda: scale_series(data, method="zscore"), rounds=1
    )
    return Metric(
        name="preprocess.scale_series.response_seconds",
        value=float(duration),
        unit="seconds",
        category="response",
        budget=1.0,
        details={"length": int(data.size)},
    )


def _normalize_df_response_time() -> Metric:
    n = 50_000
    frame = pd.DataFrame(
        {
            "ts": np.arange(n),
            "price": 100.0
            + np.cumsum(np.random.default_rng(777).normal(scale=0.1, size=n)),
            "volume": np.random.default_rng(888).lognormal(mean=10, sigma=1, size=n),
        }
    )

    duration = _measure_response_seconds(lambda: normalize_df(frame), rounds=3)
    return Metric(
        name="preprocess.normalize_df.response_seconds",
        value=float(duration),
        unit="seconds",
        category="response",
        budget=5.0,
        details={"rows": n, "rounds": 3},
    )


def collect_metrics() -> list[Metric]:
    """Gather the performance metrics that mirror CI quality gates."""

    return [
        _compute_phase_peak_memory(),
        _indicator_pipeline_peak_memory(),
        _hierarchical_features_peak_memory(),
        _compute_phase_cpu_time(),
        _kuramoto_order_cpu_time(),
        _walk_forward_response_time(),
        _strategy_response_time(),
        _scale_series_response_time(),
        _normalize_df_response_time(),
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the JSON file where collected metrics will be stored.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    metrics = collect_metrics()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": [metric.to_payload() for metric in metrics],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
