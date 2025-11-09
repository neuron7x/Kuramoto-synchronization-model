"""Monte Carlo scenario generation utilities for backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np
from numpy.typing import NDArray

from .performance import PerformanceReport, compute_performance_metrics


@dataclass(slots=True)
class MonteCarloConfig:
    """Configuration driving the stochastic scenario generation."""

    n_scenarios: int = 100
    volatility_scale: tuple[float, float] = (0.75, 1.25)
    lag_range: tuple[int, int] = (0, 5)
    dropout_probability: float = 0.0
    random_seed: int | None = None


@dataclass(slots=True)
class MonteCarloScenario:
    """Single simulated price path with metadata."""

    prices: NDArray[np.float64]
    returns: NDArray[np.float64]
    volatility_scale: float
    lag: int
    dropout_ratio: float


def _resolve_rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_monte_carlo_scenarios(
    prices: Sequence[float] | NDArray[np.float64],
    *,
    config: MonteCarloConfig | None = None,
) -> List[MonteCarloScenario]:
    """Create synthetic price paths varying volatility, lag and dropouts."""

    cfg = config or MonteCarloConfig()
    price_array = np.asarray(prices, dtype=float)
    if price_array.ndim != 1 or price_array.size < 2:
        raise ValueError("prices must be a 1-D sequence with at least two points")

    log_prices = np.log(np.clip(price_array, 1e-12, None))
    base_returns = np.diff(log_prices)
    base_mean = float(np.mean(base_returns)) if base_returns.size else 0.0
    base_std = (
        float(np.std(base_returns, ddof=1))
        if base_returns.size > 1
        else float(np.std(base_returns))
    )
    if base_std <= 0.0:
        base_std = 1e-4

    rng = _resolve_rng(cfg.random_seed)
    lag_low, lag_high = cfg.lag_range
    if lag_high < lag_low:
        raise ValueError("lag_range must be an increasing tuple")

    scenarios: List[MonteCarloScenario] = []
    for _ in range(int(cfg.n_scenarios)):
        scale = float(rng.uniform(cfg.volatility_scale[0], cfg.volatility_scale[1]))
        lag = int(rng.integers(lag_low, lag_high + 1)) if lag_high > 0 else 0
        simulated = rng.normal(
            loc=base_mean, scale=base_std * scale, size=base_returns.size
        )
        if lag > 0:
            simulated = np.roll(simulated, lag)
            simulated[:lag] = 0.0
        if cfg.dropout_probability > 0.0:
            mask = rng.random(simulated.size) < cfg.dropout_probability
            simulated[mask] = 0.0
            dropout_ratio = float(mask.mean())
        else:
            dropout_ratio = 0.0
        log_path = np.concatenate(
            ([log_prices[0]], log_prices[0] + np.cumsum(simulated))
        )
        prices_path = np.exp(log_path)
        returns = np.diff(prices_path) / prices_path[:-1]
        scenarios.append(
            MonteCarloScenario(
                prices=prices_path,
                returns=returns,
                volatility_scale=scale,
                lag=lag,
                dropout_ratio=dropout_ratio,
            )
        )
    return scenarios


def evaluate_scenarios(
    scenarios: Iterable[MonteCarloScenario],
    *,
    initial_capital: float = 1.0,
    benchmark_returns: Sequence[float] | NDArray[np.float64] | None = None,
    periods_per_year: int = 252,
) -> List[PerformanceReport]:
    """Compute performance reports for simulated paths using buy-and-hold."""

    reports: List[PerformanceReport] = []
    benchmark_array = None
    if benchmark_returns is not None:
        benchmark_array = np.asarray(benchmark_returns, dtype=float)

    for scenario in scenarios:
        equity = initial_capital * np.cumprod(1.0 + scenario.returns)
        pnl = np.diff(np.concatenate(([initial_capital], equity)))
        bench = None
        if benchmark_array is not None and benchmark_array.size:
            bench = benchmark_array[: scenario.returns.size]
        report = compute_performance_metrics(
            equity_curve=equity,
            pnl=pnl,
            position_changes=None,
            initial_capital=initial_capital,
            periods_per_year=periods_per_year,
            benchmark_returns=bench,
        )
        reports.append(report)
    return reports


__all__ = [
    "MonteCarloConfig",
    "MonteCarloScenario",
    "generate_monte_carlo_scenarios",
    "evaluate_scenarios",
]
