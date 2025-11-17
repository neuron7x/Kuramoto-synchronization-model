from __future__ import annotations

import math

import numpy as np

from execution.capital_optimizer import (
    AllocationConstraints,
    CapitalAllocationOptimizer,
    PipelineMetrics,
    TargetProfile,
)


def _weight_sum(weights: dict[str, float]) -> float:
    return sum(weights.values())


def test_optimizer_respects_bounds_and_targets() -> None:
    metrics = {
        "alpha": PipelineMetrics(0.02, 0.10, 0.15, risk_limit=0.5, min_allocation=0.10),
        "beta": PipelineMetrics(0.015, 0.08, 0.10, risk_limit=0.4, min_allocation=0.05),
        "gamma": PipelineMetrics(
            0.012, 0.06, 0.07, risk_limit=0.6, min_allocation=0.05
        ),
    }
    correlations = {
        ("alpha", "beta"): 0.3,
        ("alpha", "gamma"): 0.1,
        ("beta", "gamma"): 0.05,
    }

    optimizer = CapitalAllocationOptimizer(monte_carlo_trials=0, smoothing=0.0)
    target = TargetProfile(min_return=0.012, max_volatility=0.25, max_drawdown=0.20)
    constraints = AllocationConstraints(
        max_allocation_per_pipeline=0.55, min_allocation_per_pipeline=0.05
    )

    result = optimizer.optimise(
        metrics,
        correlations,
        target_profile=target,
        previous_allocation=None,
        constraints=constraints,
    )

    assert math.isclose(_weight_sum(result.weights), 1.0, rel_tol=1e-6, abs_tol=1e-6)
    for name, weight in result.weights.items():
        assert weight >= 0.05 - 1e-6
        assert weight <= metrics[name].risk_limit + 1e-6
    assert result.expected_return >= target.min_return - 1e-6
    assert result.volatility <= target.max_volatility + 1e-6


def test_high_correlation_encourages_diversification() -> None:
    metrics = {
        "fast": PipelineMetrics(0.03, 0.22, 0.18, risk_limit=0.6),
        "slow": PipelineMetrics(0.028, 0.21, 0.17, risk_limit=0.6),
        "alt": PipelineMetrics(0.02, 0.12, 0.09, risk_limit=0.8),
    }
    correlations = {
        ("fast", "slow"): 0.95,
        ("fast", "alt"): 0.1,
        ("slow", "alt"): 0.1,
    }

    optimizer = CapitalAllocationOptimizer(
        monte_carlo_trials=0,
        smoothing=0.0,
        risk_aversion=6.0,
        drawdown_aversion=2.5,
    )

    result = optimizer.optimise(metrics, correlations)

    assert result.weights["alt"] > 0.25
    assert result.weights["fast"] < 0.5
    assert result.weights["slow"] < 0.5


def test_turnover_constraint_limits_changes() -> None:
    metrics = {
        "alpha": PipelineMetrics(0.025, 0.11, 0.12, risk_limit=0.5),
        "beta": PipelineMetrics(0.018, 0.09, 0.09, risk_limit=0.45),
        "gamma": PipelineMetrics(0.016, 0.07, 0.08, risk_limit=0.55),
    }
    correlations = {
        ("alpha", "beta"): 0.2,
        ("alpha", "gamma"): 0.15,
        ("beta", "gamma"): 0.05,
    }
    previous = {"alpha": 0.4, "beta": 0.35, "gamma": 0.25}

    optimizer = CapitalAllocationOptimizer(monte_carlo_trials=0, smoothing=0.0)
    constraints = AllocationConstraints(max_turnover=0.2)

    result = optimizer.optimise(
        metrics,
        correlations,
        previous_allocation=previous,
        constraints=constraints,
    )

    turnover = sum(abs(result.weights[name] - previous[name]) for name in metrics)
    assert turnover <= constraints.max_turnover + 1e-6


def test_stability_validation_scales_portfolio(caplog) -> None:
    metrics = {
        "trend": PipelineMetrics(0.035, 0.35, 0.25, risk_limit=0.7),
        "carry": PipelineMetrics(0.025, 0.30, 0.22, risk_limit=0.7),
        "mean_rev": PipelineMetrics(0.02, 0.28, 0.20, risk_limit=0.7),
    }
    correlations = {
        ("trend", "carry"): 0.65,
        ("trend", "mean_rev"): 0.4,
        ("carry", "mean_rev"): 0.55,
    }

    baseline = CapitalAllocationOptimizer(
        stability_threshold=0.05,
        monte_carlo_trials=0,
        smoothing=0.0,
    ).optimise(metrics, correlations, target_profile=TargetProfile())

    optimizer = CapitalAllocationOptimizer(
        stability_threshold=0.05,
        monte_carlo_trials=512,
        smoothing=0.0,
        rng=np.random.default_rng(42),
    )
    target = TargetProfile(max_volatility=0.05, max_drawdown=0.18)

    with caplog.at_level("WARNING"):
        result = optimizer.optimise(metrics, correlations, target_profile=target)

    assert result.weights["trend"] < baseline.weights["trend"]
    assert any(
        "stability adjustment" in record.getMessage() for record in caplog.records
    )
