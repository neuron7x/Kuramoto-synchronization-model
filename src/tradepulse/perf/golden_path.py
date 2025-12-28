"""Golden Path Performance Benchmark.

This module provides the canonical performance measurement for the TradePulse
backtest golden path workflow: data ingestion → signal generation → execution → metrics.

The benchmark is designed to be:
- Deterministic (fixed seed)
- Reproducible (consistent environment capture)
- Machine-readable (structured JSON output)
- Human-readable (clear metric names and units)
"""

import logging
import os
import platform
import subprocess
import time
from typing import Any, Dict

import numpy as np

try:
    from backtest.engine import walk_forward
except ImportError:
    # Allow import in tests/CI without full backtest module
    walk_forward = None


def get_git_commit_hash() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:
        logging.getLogger(__name__).debug(
            "Failed to read git commit hash for benchmark: %s", exc
        )
    return "unknown"


def get_env_info() -> Dict[str, str]:
    """Collect environment information for reproducibility."""
    return {
        "python_version": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "commit_hash": get_git_commit_hash(),
        "numpy_version": np.__version__ if hasattr(np, "__version__") else "unknown",
    }


def generate_benchmark_data(n_bars: int = 252, seed: int = 42) -> np.ndarray:
    """Generate deterministic synthetic price data for benchmarking.

    Parameters
    ----------
    n_bars : int
        Number of bars to generate (default: 252 for 1 year of daily data)
    seed : int
        Random seed for reproducibility

    Returns
    -------
    np.ndarray
        Price data array
    """
    np.random.seed(seed)
    initial_price = 100.0
    drift = 0.0002  # 0.02% daily drift
    volatility = 0.01  # 1% daily volatility

    returns = np.random.normal(drift, volatility, n_bars)
    prices = initial_price * np.cumprod(1 + returns)

    # Ensure all prices are positive
    prices = np.maximum(prices, 1.0)

    return prices


def momentum_signal(prices: np.ndarray, lookback: int = 10) -> np.ndarray:
    """Simple momentum strategy for benchmarking."""
    signal = np.zeros_like(prices)

    for i in range(lookback, len(prices)):
        ma = np.mean(prices[i-lookback:i])
        if prices[i] > ma:
            signal[i] = 1.0
        elif prices[i] < ma:
            signal[i] = -1.0

    return signal


def run_golden_path_bench(
    n_bars: int = 252,
    n_iterations: int = 100,
    seed: int = 42,
) -> Dict[str, Any]:
    """Run the canonical golden path performance benchmark.

    This function measures the performance of the core backtest workflow
    over multiple iterations to calculate latency percentiles and throughput.

    Parameters
    ----------
    n_bars : int
        Number of price bars to use in backtest
    n_iterations : int
        Number of benchmark iterations to run
    seed : int
        Random seed for reproducibility

    Returns
    -------
    Dict[str, Any]
        Performance metrics including:
        - env: Environment information (python version, OS, commit hash)
        - latency_ms: Latency statistics (p50, p95, p99, mean, min, max)
        - throughput: Events/bars processed per second
        - memory_peak_mb: Estimated peak memory usage (if available)
        - config: Benchmark configuration (n_bars, n_iterations, seed)

    Raises
    ------
    ValueError
        If latency measurements are invalid (NaN, inf, or non-positive)
    RuntimeError
        If walk_forward is not available
    """
    if walk_forward is None:
        raise RuntimeError(
            "backtest.engine.walk_forward is not available. "
            "Ensure backtest module is installed."
        )

    # Generate benchmark data once
    prices = generate_benchmark_data(n_bars=n_bars, seed=seed)

    # Warm-up run
    _ = walk_forward(
        prices,
        momentum_signal,
        fee=0.001,
        strategy_name="warmup",
    )

    # Benchmark runs
    latencies = []
    for _ in range(n_iterations):
        start = time.perf_counter()
        _ = walk_forward(
            prices,
            momentum_signal,
            fee=0.001,
            strategy_name="benchmark",
        )
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # Convert to milliseconds

    # Calculate statistics
    latencies_array = np.array(latencies)

    # Validate latencies
    if not np.all(np.isfinite(latencies_array)):
        raise ValueError(
            f"Latency measurements contain non-finite values: {latencies_array}"
        )

    if not np.all(latencies_array > 0):
        raise ValueError(
            f"Latency measurements contain non-positive values: {latencies_array}"
        )

    p50 = float(np.percentile(latencies_array, 50))
    p95 = float(np.percentile(latencies_array, 95))
    p99 = float(np.percentile(latencies_array, 99))
    mean_latency = float(np.mean(latencies_array))
    min_latency = float(np.min(latencies_array))
    max_latency = float(np.max(latencies_array))

    # Calculate throughput (bars per second)
    # Use p50 latency for throughput calculation
    throughput = (n_bars / (p50 / 1000.0)) if p50 > 0 else 0.0

    # Try to get memory usage (basic estimation)
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
    except ImportError:
        memory_mb = None

    # Build results dictionary
    results = {
        "env": get_env_info(),
        "latency_ms": {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "mean": mean_latency,
            "min": min_latency,
            "max": max_latency,
        },
        "throughput": {
            "bars_per_second": throughput,
            "iterations_per_second": 1000.0 / mean_latency if mean_latency > 0 else 0.0,
        },
        "config": {
            "n_bars": n_bars,
            "n_iterations": n_iterations,
            "seed": seed,
        },
    }

    if memory_mb is not None:
        results["memory_peak_mb"] = memory_mb

    return results
