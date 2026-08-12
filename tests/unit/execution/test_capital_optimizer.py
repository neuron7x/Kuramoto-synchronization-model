# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.capital_optimizer — target uncovered lines."""

from __future__ import annotations

import numpy as np
import pytest

from execution.capital_optimizer import (
    AllocationConstraints,
    AllocationResult,
    CapitalAllocationOptimizer,
    PipelineMetrics,
    TargetProfile,
)

# ── PipelineMetrics validation ──────────────────────────────────────


class TestPipelineMetrics:
    def test_valid_construction(self):
        pm = PipelineMetrics(expected_return=0.05, volatility=0.1, max_drawdown=0.2)
        assert pm.volatility == 0.1

    def test_negative_volatility_raises(self):
        with pytest.raises(ValueError, match="volatility"):
            PipelineMetrics(expected_return=0.05, volatility=-0.1, max_drawdown=0.2)

    def test_negative_drawdown_raises(self):
        with pytest.raises(ValueError, match="max_drawdown"):
            PipelineMetrics(expected_return=0.05, volatility=0.1, max_drawdown=-0.1)

    def test_negative_min_allocation_raises(self):
        with pytest.raises(ValueError, match="min_allocation"):
            PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.2,
                min_allocation=-0.1,
            )

    def test_risk_limit_zero_raises(self):
        with pytest.raises(ValueError, match="risk_limit"):
            PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.2,
                risk_limit=0.0,
            )

    def test_risk_limit_negative_raises(self):
        with pytest.raises(ValueError, match="risk_limit"):
            PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.2,
                risk_limit=-1.0,
            )

    def test_min_allocation_exceeds_risk_limit(self):
        with pytest.raises(ValueError, match="min_allocation must not exceed"):
            PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.2,
                risk_limit=0.3,
                min_allocation=0.5,
            )


# ── TargetProfile validation ────────────────────────────────────────


class TestTargetProfile:
    def test_defaults(self):
        tp = TargetProfile()
        assert tp.min_return is None

    def test_max_volatility_zero_raises(self):
        with pytest.raises(ValueError, match="max_volatility"):
            TargetProfile(max_volatility=0.0)

    def test_max_volatility_negative_raises(self):
        with pytest.raises(ValueError, match="max_volatility"):
            TargetProfile(max_volatility=-1.0)

    def test_max_drawdown_negative_raises(self):
        with pytest.raises(ValueError, match="max_drawdown"):
            TargetProfile(max_drawdown=-0.1)


# ── AllocationConstraints validation ────────────────────────────────


class TestAllocationConstraints:
    def test_defaults(self):
        ac = AllocationConstraints()
        assert ac.total_risk_limit is None

    def test_total_risk_limit_zero_raises(self):
        with pytest.raises(ValueError, match="total_risk_limit"):
            AllocationConstraints(total_risk_limit=0.0)

    def test_max_turnover_zero_raises(self):
        with pytest.raises(ValueError, match="max_turnover"):
            AllocationConstraints(max_turnover=0.0)

    def test_max_allocation_per_pipeline_zero_raises(self):
        with pytest.raises(ValueError, match="max_allocation_per_pipeline"):
            AllocationConstraints(max_allocation_per_pipeline=0.0)

    def test_min_allocation_per_pipeline_negative_raises(self):
        with pytest.raises(ValueError, match="min_allocation_per_pipeline"):
            AllocationConstraints(min_allocation_per_pipeline=-0.1)


# ── Optimizer constructor validation ────────────────────────────────


class TestOptimizerInit:
    def test_risk_aversion_zero_raises(self):
        with pytest.raises(ValueError, match="risk_aversion"):
            CapitalAllocationOptimizer(risk_aversion=0.0)

    def test_drawdown_aversion_zero_raises(self):
        with pytest.raises(ValueError, match="drawdown_aversion"):
            CapitalAllocationOptimizer(drawdown_aversion=0.0)

    def test_turnover_aversion_negative_raises(self):
        with pytest.raises(ValueError, match="turnover_aversion"):
            CapitalAllocationOptimizer(turnover_aversion=-1.0)

    def test_stability_threshold_zero_raises(self):
        with pytest.raises(ValueError, match="stability_threshold"):
            CapitalAllocationOptimizer(stability_threshold=0.0)

    def test_monte_carlo_trials_negative_raises(self):
        with pytest.raises(ValueError, match="monte_carlo_trials"):
            CapitalAllocationOptimizer(monte_carlo_trials=-1)

    def test_smoothing_out_of_range_raises(self):
        with pytest.raises(ValueError, match="smoothing"):
            CapitalAllocationOptimizer(smoothing=1.5)

    def test_max_iterations_zero_raises(self):
        with pytest.raises(ValueError, match="max_iterations"):
            CapitalAllocationOptimizer(max_iterations=0)

    def test_tolerance_zero_raises(self):
        with pytest.raises(ValueError, match="tolerance"):
            CapitalAllocationOptimizer(tolerance=0.0)


# ── Helpers ─────────────────────────────────────────────────────────


def _make_metrics(n: int = 3) -> dict[str, PipelineMetrics]:
    """Return *n* pipeline metrics with reproducible parameters."""
    return {
        f"pipe_{i}": PipelineMetrics(
            expected_return=0.03 + 0.01 * i,
            volatility=0.10 + 0.02 * i,
            max_drawdown=0.05 + 0.01 * i,
        )
        for i in range(n)
    }


def _make_correlations_tuple(names: list[str]) -> dict[tuple[str, str], float]:
    return {(a, b): 0.3 for i, a in enumerate(names) for b in names[i + 1 :]}


def _make_correlations_nested(names: list[str]) -> dict[str, dict[str, float]]:
    nested: dict[str, dict[str, float]] = {}
    for a in names:
        nested[a] = {}
        for b in names:
            if a != b:
                nested[a][b] = 0.3
    return nested


# ── Core optimise / reallocate tests ────────────────────────────────


class TestOptimise:
    def test_empty_metrics_raises(self):
        opt = CapitalAllocationOptimizer(rng=np.random.default_rng(0))
        with pytest.raises(ValueError, match="must not be empty"):
            opt.optimise({}, {})

    def test_basic_optimise_tuple_correlations(self):
        metrics = _make_metrics(3)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=64,
            rng=np.random.default_rng(42),
        )
        result = opt.optimise(metrics, corr)
        assert isinstance(result, AllocationResult)
        assert abs(sum(result.weights.values()) - 1.0) < 0.05
        assert result.volatility >= 0.0

    def test_basic_optimise_nested_correlations(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_nested(names)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=64,
            rng=np.random.default_rng(7),
        )
        result = opt.optimise(metrics, corr)
        assert set(result.weights.keys()) == set(names)

    def test_reallocate_delegates_to_optimise(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.reallocate(metrics, corr)
        assert isinstance(result, AllocationResult)

    def test_correlation_out_of_range_raises(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = {(names[0], names[1]): 1.5}
        opt = CapitalAllocationOptimizer(rng=np.random.default_rng(0))
        with pytest.raises(ValueError, match="Correlation"):
            opt.optimise(metrics, corr)


# ── Constraints ─────────────────────────────────────────────────────


class TestConstraints:
    def test_max_allocation_per_pipeline_applied(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        constraints = AllocationConstraints(max_allocation_per_pipeline=0.6)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, constraints=constraints)
        for w in result.weights.values():
            assert w <= 0.6 + 0.05  # small tolerance for projection

    def test_min_allocation_per_pipeline_constraint(self):
        metrics = _make_metrics(3)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        constraints = AllocationConstraints(min_allocation_per_pipeline=0.1)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(1),
        )
        result = opt.optimise(metrics, corr, constraints=constraints)
        for w in result.weights.values():
            assert w >= 0.1 - 0.02

    def test_lower_exceeds_upper_raises(self):
        # Use constraints to force lower > upper without triggering PipelineMetrics validation
        metrics = {
            "a": PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.1,
                risk_limit=0.3,
                min_allocation=0.2,
            ),
        }
        corr: dict[tuple[str, str], float] = {}
        constraints = AllocationConstraints(
            max_allocation_per_pipeline=0.1,
            min_allocation_per_pipeline=0.5,
        )
        opt = CapitalAllocationOptimizer(rng=np.random.default_rng(0))
        with pytest.raises(ValueError, match="Lower bounds exceed"):
            opt.optimise(metrics, corr, constraints=constraints)

    def test_sum_of_min_allocations_exceeds_capital(self):
        metrics = {
            f"p{i}": PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.1,
                min_allocation=0.4,
            )
            for i in range(4)
        }
        corr: dict[tuple[str, str], float] = {}
        opt = CapitalAllocationOptimizer(rng=np.random.default_rng(0))
        with pytest.raises(ValueError, match="Sum of minimum"):
            opt.optimise(metrics, corr)


# ── Previous allocation / turnover ──────────────────────────────────


class TestPreviousAllocation:
    def test_with_previous_allocation(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        prev = {names[0]: 0.6, names[1]: 0.4}
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            smoothing=0.5,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, previous_allocation=prev)
        assert isinstance(result, AllocationResult)

    def test_turnover_constraint(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        prev = {names[0]: 0.7, names[1]: 0.3}
        constraints = AllocationConstraints(max_turnover=0.1)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(
            metrics,
            corr,
            previous_allocation=prev,
            constraints=constraints,
        )
        assert isinstance(result, AllocationResult)

    def test_smoothing_zero_bypasses_blend(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        prev = {names[0]: 0.5, names[1]: 0.5}
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            smoothing=0.0,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, previous_allocation=prev)
        assert isinstance(result, AllocationResult)


# ── TargetProfile interactions ──────────────────────────────────────


class TestTargetProfileOptimise:
    def test_min_return_target(self):
        metrics = _make_metrics(3)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        tp = TargetProfile(min_return=0.10)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, target_profile=tp)
        assert isinstance(result, AllocationResult)

    def test_max_volatility_target(self):
        metrics = _make_metrics(3)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        tp = TargetProfile(max_volatility=0.01)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=64,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, target_profile=tp)
        assert isinstance(result, AllocationResult)

    def test_max_drawdown_target(self):
        metrics = _make_metrics(3)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        tp = TargetProfile(max_drawdown=0.001)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=64,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, target_profile=tp)
        assert isinstance(result, AllocationResult)


# ── Monte Carlo 0 → stability shortcut ──────────────────────────────


class TestZeroMonteCarlo:
    def test_skip_stability_validation(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=0,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr)
        assert isinstance(result, AllocationResult)


# ── Pipeline with risk_limit ────────────────────────────────────────


class TestRiskLimit:
    def test_risk_limit_caps_upper_bound(self):
        metrics = {
            "a": PipelineMetrics(
                expected_return=0.05,
                volatility=0.1,
                max_drawdown=0.1,
                risk_limit=0.4,
            ),
            "b": PipelineMetrics(
                expected_return=0.04,
                volatility=0.1,
                max_drawdown=0.1,
            ),
        }
        corr = {("a", "b"): 0.2}
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr)
        assert result.weights["a"] <= 0.4 + 0.05

    def test_total_risk_limit_constraint(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        constraints = AllocationConstraints(total_risk_limit=0.005)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=64,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr, constraints=constraints)
        assert isinstance(result, AllocationResult)


# ── AllocationResult notes ──────────────────────────────────────────


class TestAllocationResultNotes:
    def test_notes_populated(self):
        metrics = _make_metrics(2)
        names = sorted(metrics.keys())
        corr = _make_correlations_tuple(names)
        opt = CapitalAllocationOptimizer(
            monte_carlo_trials=32,
            rng=np.random.default_rng(0),
        )
        result = opt.optimise(metrics, corr)
        assert "portfolio_return" in result.notes
        assert "portfolio_volatility" in result.notes
        assert "portfolio_drawdown" in result.notes
        assert "stability_score" in result.notes
