# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capital allocation optimiser considering portfolio risk interactions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineMetrics:
    """Snapshot of risk/return attributes for a capital deployment pipeline."""

    expected_return: float
    volatility: float
    max_drawdown: float
    risk_limit: float | None = None
    min_allocation: float = 0.0

    def __post_init__(self) -> None:
        if self.volatility < 0.0:
            raise ValueError("volatility must be non-negative")
        if self.max_drawdown < 0.0:
            raise ValueError("max_drawdown must be non-negative")
        if self.min_allocation < 0.0:
            raise ValueError("min_allocation must be non-negative")
        if self.risk_limit is not None and self.risk_limit <= 0.0:
            raise ValueError("risk_limit must be positive when provided")
        if self.risk_limit is not None and self.min_allocation > self.risk_limit:
            raise ValueError("min_allocation must not exceed risk_limit")


@dataclass(slots=True)
class TargetProfile:
    """Portfolio level targets that the optimiser tries to respect."""

    min_return: float | None = None
    max_volatility: float | None = None
    max_drawdown: float | None = None

    def __post_init__(self) -> None:
        if self.max_volatility is not None and self.max_volatility <= 0.0:
            raise ValueError("max_volatility must be positive when provided")
        if self.max_drawdown is not None and self.max_drawdown < 0.0:
            raise ValueError("max_drawdown must be non-negative when provided")


@dataclass(slots=True)
class AllocationConstraints:
    """Hard constraints applied across all pipelines."""

    total_risk_limit: float | None = None
    max_turnover: float | None = None
    max_allocation_per_pipeline: float | None = None
    min_allocation_per_pipeline: float = 0.0

    def __post_init__(self) -> None:
        if self.total_risk_limit is not None and self.total_risk_limit <= 0.0:
            raise ValueError("total_risk_limit must be positive when provided")
        if self.max_turnover is not None and self.max_turnover <= 0.0:
            raise ValueError("max_turnover must be positive when provided")
        if self.max_allocation_per_pipeline is not None and (
            self.max_allocation_per_pipeline <= 0.0
        ):
            raise ValueError("max_allocation_per_pipeline must be positive when provided")
        if self.min_allocation_per_pipeline < 0.0:
            raise ValueError("min_allocation_per_pipeline must be non-negative")


@dataclass(slots=True)
class AllocationResult:
    """Result produced by :class:`CapitalAllocationOptimizer`."""

    weights: dict[str, float]
    expected_return: float
    volatility: float
    max_drawdown: float
    stability_score: float
    notes: dict[str, float]


class CapitalAllocationOptimizer:
    """Allocate capital across pipelines under correlation-aware risk controls."""

    def __init__(
        self,
        *,
        risk_aversion: float = 4.0,
        drawdown_aversion: float = 2.0,
        turnover_aversion: float = 1.5,
        stability_threshold: float = 0.02,
        monte_carlo_trials: int = 1024,
        smoothing: float = 0.25,
        rng: np.random.Generator | None = None,
        max_iterations: int = 250,
        tolerance: float = 1e-6,
    ) -> None:
        if risk_aversion <= 0.0:
            raise ValueError("risk_aversion must be positive")
        if drawdown_aversion <= 0.0:
            raise ValueError("drawdown_aversion must be positive")
        if turnover_aversion < 0.0:
            raise ValueError("turnover_aversion must be non-negative")
        if stability_threshold <= 0.0:
            raise ValueError("stability_threshold must be positive")
        if monte_carlo_trials < 0:
            raise ValueError("monte_carlo_trials must be non-negative")
        if not 0.0 <= smoothing <= 1.0:
            raise ValueError("smoothing must be between 0 and 1")
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if tolerance <= 0.0:
            raise ValueError("tolerance must be positive")

        self._risk_aversion = risk_aversion
        self._drawdown_aversion = drawdown_aversion
        self._turnover_aversion = turnover_aversion
        self._stability_threshold = stability_threshold
        self._monte_carlo_trials = monte_carlo_trials
        self._smoothing = smoothing
        self._rng = rng or np.random.default_rng()
        self._max_iterations = max_iterations
        self._tolerance = tolerance

    # ------------------------------------------------------------------
    def optimise(
        self,
        metrics: Mapping[str, PipelineMetrics],
        correlations: Mapping[tuple[str, str], float] | Mapping[str, Mapping[str, float]],
        *,
        target_profile: TargetProfile | None = None,
        previous_allocation: Mapping[str, float] | None = None,
        constraints: AllocationConstraints | None = None,
    ) -> AllocationResult:
        """Optimise the capital distribution across the provided pipelines."""

        if not metrics:
            raise ValueError("metrics must not be empty")

        names = sorted(metrics.keys())
        size = len(names)
        expected = np.fromiter((metrics[name].expected_return for name in names), float)
        volatility = np.fromiter((metrics[name].volatility for name in names), float)
        drawdown = np.fromiter((metrics[name].max_drawdown for name in names), float)

        lower_bounds = np.fromiter((metrics[name].min_allocation for name in names), float)
        upper_bounds = np.empty(size, dtype=float)
        for idx, name in enumerate(names):
            limit = metrics[name].risk_limit
            upper_bounds[idx] = min(limit, 1.0) if limit is not None else 1.0

        if constraints is not None:
            if constraints.max_allocation_per_pipeline is not None:
                upper_bounds = np.minimum(upper_bounds, constraints.max_allocation_per_pipeline)
            if constraints.min_allocation_per_pipeline:
                lower_bounds = np.maximum(lower_bounds, constraints.min_allocation_per_pipeline)

        if np.any(lower_bounds > upper_bounds + 1e-12):
            raise ValueError("Lower bounds exceed upper bounds for one or more pipelines")

        total_min = float(lower_bounds.sum())
        if total_min > 1.0 + 1e-9:
            raise ValueError("Sum of minimum allocations exceeds 100% of capital")

        covariance = self._build_covariance_matrix(names, metrics, correlations, volatility)

        weights = self._initialise_weights(
            names,
            lower_bounds,
            upper_bounds,
            previous_allocation,
        )

        weights = self._iterate(
            names,
            weights,
            expected,
            covariance,
            drawdown,
            lower_bounds,
            upper_bounds,
            target_profile,
            previous_allocation,
            constraints,
        )

        portfolio_return = float(expected @ weights)
        portfolio_volatility = float(np.sqrt(weights @ covariance @ weights))
        approx_drawdown = float(np.clip(drawdown @ weights, 0.0, None))

        weights, stability = self._validate_stability(
            weights,
            expected,
            covariance,
            lower_bounds,
            upper_bounds,
            target_profile,
            constraints,
        )

        portfolio_return = float(expected @ weights)
        portfolio_volatility = float(np.sqrt(max(weights @ covariance @ weights, 0.0)))
        approx_drawdown = float(np.clip(drawdown @ weights, 0.0, None))

        result_weights: dict[str, float] = {
            name: float(weights[idx]) for idx, name in enumerate(names)
        }

        notes: dict[str, float] = {
            "portfolio_return": portfolio_return,
            "portfolio_volatility": portfolio_volatility,
            "portfolio_drawdown": approx_drawdown,
            "stability_score": stability,
        }

        logger.info(
            "capital-allocation decision",
            extra={
                "allocations": result_weights,
                "expected_return": portfolio_return,
                "volatility": portfolio_volatility,
                "drawdown": approx_drawdown,
                "stability": stability,
            },
        )

        return AllocationResult(
            weights=result_weights,
            expected_return=portfolio_return,
            volatility=portfolio_volatility,
            max_drawdown=approx_drawdown,
            stability_score=stability,
            notes=notes,
        )

    # ------------------------------------------------------------------
    def reallocate(
        self,
        metrics: Mapping[str, PipelineMetrics],
        correlations: Mapping[tuple[str, str], float] | Mapping[str, Mapping[str, float]],
        *,
        target_profile: TargetProfile | None = None,
        previous_allocation: Mapping[str, float] | None = None,
        constraints: AllocationConstraints | None = None,
    ) -> AllocationResult:
        """Alias of :meth:`optimise` emphasising dynamic reallocations."""

        return self.optimise(
            metrics,
            correlations,
            target_profile=target_profile,
            previous_allocation=previous_allocation,
            constraints=constraints,
        )

    # ------------------------------------------------------------------
    def _build_covariance_matrix(
        self,
        names: list[str],
        metrics: Mapping[str, PipelineMetrics],
        correlations: Mapping[tuple[str, str], float] | Mapping[str, Mapping[str, float]],
        volatility: np.ndarray,
    ) -> np.ndarray:
        size = len(names)
        corr_matrix = np.eye(size)

        def lookup(a: str, b: str) -> float:
            if isinstance(correlations, Mapping) and all(
                isinstance(key, tuple) and len(key) == 2 for key in correlations.keys()
            ):
                value = correlations.get((a, b))
                if value is None:
                    value = correlations.get((b, a), 0.0)
                return float(value) if value is not None else 0.0
            nested = correlations.get(a)
            if not nested:
                return 0.0
            value = nested.get(b)
            if value is None:
                value = nested.get(a)
            return float(value) if value is not None else 0.0

        for i, name_i in enumerate(names):
            for j in range(i + 1, size):
                name_j = names[j]
                value = lookup(name_i, name_j)
                if not -1.0 <= value <= 1.0:
                    raise ValueError(
                        f"Correlation between {name_i} and {name_j} must be in [-1, 1]"
                    )
                corr_matrix[i, j] = corr_matrix[j, i] = value

        covariance = np.outer(volatility, volatility) * corr_matrix

        # Numerical stabilisation: ensure covariance is positive semi-definite.
        min_eig = np.linalg.eigvalsh(covariance).min()
        if min_eig < 0.0:
            covariance += np.eye(size) * (abs(min_eig) + 1e-8)

        return covariance

    # ------------------------------------------------------------------
    def _initialise_weights(
        self,
        names: list[str],
        lower: np.ndarray,
        upper: np.ndarray,
        previous_allocation: Mapping[str, float] | None,
    ) -> np.ndarray:
        size = len(names)
        if previous_allocation:
            weights = np.fromiter((previous_allocation.get(name, 0.0) for name in names), float)
            weights = self._project(weights, lower, upper)
            weights = self._blend_with_previous(weights, previous_allocation, names)
        else:
            weights = np.full(size, 1.0 / size)
            weights = np.clip(weights, lower, None)
        return self._project(weights, lower, upper)

    # ------------------------------------------------------------------
    def _blend_with_previous(
        self,
        weights: np.ndarray,
        previous: Mapping[str, float],
        names: list[str],
    ) -> np.ndarray:
        if self._smoothing == 0.0:
            return weights
        prev = np.fromiter((previous.get(name, 0.0) for name in names), float)
        blended = self._smoothing * weights + (1.0 - self._smoothing) * prev
        return blended

    # ------------------------------------------------------------------
    def _iterate(
        self,
        names: list[str],
        weights: np.ndarray,
        expected: np.ndarray,
        covariance: np.ndarray,
        drawdown: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        target_profile: TargetProfile | None,
        previous_allocation: Mapping[str, float] | None,
        constraints: AllocationConstraints | None,
    ) -> np.ndarray:
        prev_weights = weights.copy()
        step_size = 0.1

        turnover_target = None
        if constraints and constraints.max_turnover is not None and previous_allocation:
            turnover_target = constraints.max_turnover

        previous_vec = None
        if previous_allocation:
            previous_vec = np.fromiter(
                (previous_allocation.get(name, 0.0) for name in names), float
            )
            previous_vec = self._project(previous_vec, lower, upper)

        for iteration in range(self._max_iterations):
            gradient = -expected + (2.0 * self._risk_aversion) * (covariance @ weights)
            gradient += self._drawdown_aversion * drawdown

            if previous_vec is not None:
                gradient += self._turnover_aversion * (weights - previous_vec)

            weights -= step_size * gradient
            weights = self._project(weights, lower, upper)

            if target_profile and target_profile.min_return is not None:
                realised = float(expected @ weights)
                shortfall = target_profile.min_return - realised
                if shortfall > 0.0:
                    boost_index = int(np.argmax(expected))
                    capacity = upper[boost_index] - weights[boost_index]
                    if capacity > 0.0:
                        adjustment = min(shortfall / max(expected[boost_index], 1e-9), capacity)
                        weights[boost_index] += adjustment
                        weights = self._project(weights, lower, upper)

            if turnover_target is not None and previous_vec is not None:
                turnover = float(np.sum(np.abs(weights - previous_vec)))
                if turnover > turnover_target:
                    scale = turnover_target / turnover
                    weights = previous_vec + (weights - previous_vec) * scale
                    weights = self._project(weights, lower, upper)

            delta = float(np.linalg.norm(weights - prev_weights, ord=2))
            if delta < self._tolerance:
                break
            prev_weights = weights.copy()

        return weights

    # ------------------------------------------------------------------
    def _project(self, weights: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
        weights = np.clip(weights, lower, upper)

        for _ in range(10):
            total = float(weights.sum())
            if abs(total - 1.0) < 1e-9:
                break
            if total == 0.0:
                weights = lower.copy()
                residual = max(0.0, 1.0 - float(weights.sum()))
                if residual > 0.0:
                    capacity = upper - weights
                    capacity_sum = float(capacity.sum())
                    if capacity_sum > 0.0:
                        weights += capacity * (residual / capacity_sum)
                weights = np.clip(weights, lower, upper)
                continue

            if total > 1.0:
                excess = total - 1.0
                adjustable = weights - lower
                adj_sum = float(adjustable.sum())
                if adj_sum > 0.0:
                    weights -= adjustable / adj_sum * excess
            else:
                deficit = 1.0 - total
                adjustable = upper - weights
                adj_sum = float(adjustable.sum())
                if adj_sum > 0.0:
                    weights += adjustable / adj_sum * deficit
            weights = np.clip(weights, lower, upper)

        total = float(weights.sum())
        if total > 0.0:
            weights /= total
        else:
            weights = lower.copy()
            total = float(weights.sum())
            if total > 0.0:
                weights /= total
        return np.clip(weights, lower, upper)

    # ------------------------------------------------------------------
    def _validate_stability(
        self,
        weights: np.ndarray,
        expected: np.ndarray,
        covariance: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        target_profile: TargetProfile | None,
        constraints: AllocationConstraints | None,
    ) -> tuple[np.ndarray, float]:
        if self._monte_carlo_trials == 0:
            return weights, float(expected @ weights)

        try:
            samples = self._rng.multivariate_normal(
                mean=expected,
                cov=covariance,
                size=self._monte_carlo_trials,
                check_valid="ignore",
            )
        except np.linalg.LinAlgError:
            jitter = np.eye(len(weights)) * 1e-6
            samples = self._rng.multivariate_normal(
                mean=expected,
                cov=covariance + jitter,
                size=self._monte_carlo_trials,
                check_valid="ignore",
            )

        portfolio_returns = samples @ weights
        volatility = float(np.std(portfolio_returns))

        cumulative = np.cumprod(1.0 + portfolio_returns) - 1.0
        drawdowns = np.maximum.accumulate(cumulative) - cumulative
        simulated_drawdown = float(np.max(drawdowns, initial=0.0))

        scaling_factors: list[float] = []

        vol_limits = [self._stability_threshold]
        if target_profile and target_profile.max_volatility is not None:
            vol_limits.append(target_profile.max_volatility)
        if constraints and constraints.total_risk_limit is not None:
            vol_limits.append(constraints.total_risk_limit)
        limit = min(vol_limits)
        if volatility > limit and volatility > 0.0:
            scaling_factors.append(limit / volatility)

        if target_profile and target_profile.max_drawdown is not None:
            if simulated_drawdown > target_profile.max_drawdown and simulated_drawdown > 0.0:
                scaling_factors.append(target_profile.max_drawdown / simulated_drawdown)

        if scaling_factors:
            scale = min(scaling_factors)
            try:
                inv_cov = np.linalg.pinv(covariance)
            except np.linalg.LinAlgError:
                inv_cov = np.linalg.pinv(covariance + np.eye(len(weights)) * 1e-6)

            ones = np.ones(len(weights))
            denom = float(ones @ inv_cov @ ones)
            if denom <= 0.0:
                min_var_weights = np.full(len(weights), 1.0 / len(weights))
            else:
                min_var_weights = (inv_cov @ ones) / denom

            min_var_weights = np.clip(min_var_weights, lower, upper)
            min_var_weights = self._project(min_var_weights, lower, upper)

            blended = scale * min_var_weights + (1.0 - scale) * weights
            weights = self._project(blended, lower, upper)
            logger.warning(
                "capital-allocation stability adjustment",
                extra={
                    "scale": scale,
                    "simulated_volatility": volatility,
                    "simulated_drawdown": simulated_drawdown,
                },
            )

        stability_score = float(np.mean(portfolio_returns))
        return weights, stability_score


__all__ = [
    "PipelineMetrics",
    "TargetProfile",
    "AllocationConstraints",
    "AllocationResult",
    "CapitalAllocationOptimizer",
]
