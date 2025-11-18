from __future__ import annotations

import numpy as np

from backtest.resampling import (
    bayesian_mcmc_performance_metrics,
    bootstrap_performance_metrics,
)


def _make_equity(initial_capital: float, returns: np.ndarray) -> np.ndarray:
    return initial_capital * np.cumprod(1.0 + returns)


def test_bootstrap_confidence_interval_contains_point_estimate() -> None:
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.01, size=180)
    initial_capital = 100_000.0
    equity = _make_equity(initial_capital, returns)

    result = bootstrap_performance_metrics(
        equity_curve=equity,
        initial_capital=initial_capital,
        confidence_level=0.9,
        num_resamples=96,
        random_state=1,
    )

    sharpe = result.metrics["sharpe_ratio"]
    assert sharpe.samples.shape == (96,)
    assert sharpe.ci_lower is not None and sharpe.ci_upper is not None
    assert sharpe.ci_lower <= sharpe.ci_upper
    if sharpe.point_estimate is not None:
        assert sharpe.ci_lower - 1e-12 <= sharpe.point_estimate <= sharpe.ci_upper + 1e-12


def test_bootstrap_rejects_unknown_metric_name() -> None:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.005, size=32)
    initial_capital = 25_000.0
    equity = _make_equity(initial_capital, returns)

    try:
        bootstrap_performance_metrics(
            equity_curve=equity,
            initial_capital=initial_capital,
            metrics=("nonexistent",),
        )
    except ValueError as exc:
        assert "Unknown metrics" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for invalid metric selection")


def test_bayesian_mcmc_generates_reasonable_distributions() -> None:
    rng = np.random.default_rng(11)
    returns = rng.normal(0.002, 0.007, size=220)
    initial_capital = 75_000.0
    equity = _make_equity(initial_capital, returns)

    result = bayesian_mcmc_performance_metrics(
        equity_curve=equity,
        initial_capital=initial_capital,
        confidence_level=0.9,
        num_samples=128,
        random_state=5,
    )

    cagr_metric = result.metrics["cagr"]
    assert cagr_metric.samples.shape == (128,)
    assert cagr_metric.ci_lower is not None and cagr_metric.ci_upper is not None
    assert cagr_metric.ci_lower <= cagr_metric.ci_upper


def test_bayesian_mcmc_rejects_empty_equity_curve() -> None:
    try:
        bayesian_mcmc_performance_metrics(
            equity_curve=[],
            initial_capital=1_000.0,
        )
    except ValueError as exc:
        assert "equity_curve" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for empty equity curve")
