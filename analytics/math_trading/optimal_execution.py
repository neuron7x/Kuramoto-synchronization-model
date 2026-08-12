# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Almgren-Chriss optimal execution model implementation.

This module provides an implementation of the Almgren-Chriss framework for
optimal trade execution. The model minimizes a combination of market impact
costs and execution risk while slicing large orders.

The implementation follows:
    Almgren, R. and Chriss, N. (2000). "Optimal execution of portfolio transactions."
    Journal of Risk, 3(2), 5-39.

Key components:
    - Temporary impact: Market impact that reverts immediately
    - Permanent impact: Lasting effect on price from trading
    - Risk penalty: Variance cost from execution uncertainty
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class OptimalExecutionParams:
    """Parameters for Almgren-Chriss optimal execution.

    Attributes:
        total_quantity: Total shares/units to execute (positive for buy).
        duration_seconds: Total execution window in seconds.
        volatility: Annualized volatility of the asset.
        temporary_impact: Temporary impact coefficient (eta).
        permanent_impact: Permanent impact coefficient (gamma).
        risk_aversion: Risk aversion parameter (lambda).
        daily_volume: Average daily trading volume (optional, for scaling).
    """

    total_quantity: float
    duration_seconds: float
    volatility: float
    temporary_impact: float
    permanent_impact: float
    risk_aversion: float = 1e-6
    daily_volume: float | None = None

    def __post_init__(self) -> None:
        if self.total_quantity == 0:
            raise ValueError("total_quantity must be non-zero")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.volatility <= 0:
            raise ValueError("volatility must be positive")
        if self.temporary_impact < 0:
            raise ValueError("temporary_impact must be non-negative")
        if self.permanent_impact < 0:
            raise ValueError("permanent_impact must be non-negative")
        if self.risk_aversion < 0:
            raise ValueError("risk_aversion must be non-negative")


@dataclass(frozen=True, slots=True)
class ExecutionSlice:
    """A single slice of the execution schedule.

    Attributes:
        time_offset: Time offset from start in seconds.
        quantity: Quantity to execute in this slice.
        expected_price_impact: Expected temporary price impact.
        cumulative_quantity: Cumulative quantity executed up to this slice.
        remaining_quantity: Quantity remaining after this slice.
    """

    time_offset: float
    quantity: float
    expected_price_impact: float
    cumulative_quantity: float
    remaining_quantity: float


@dataclass(frozen=True, slots=True)
class OptimalExecutionResult:
    """Result of optimal execution computation.

    Attributes:
        slices: Ordered list of execution slices.
        total_expected_cost: Total expected execution cost (impact + risk).
        expected_shortfall: Expected implementation shortfall.
        execution_risk: Variance of execution cost.
        urgency_parameter: Computed kappa (urgency of execution).
    """

    slices: tuple[ExecutionSlice, ...]
    total_expected_cost: float
    expected_shortfall: float
    execution_risk: float
    urgency_parameter: float

    def to_dict(self) -> dict:
        return {
            "slices": [
                {
                    "time_offset": s.time_offset,
                    "quantity": s.quantity,
                    "expected_price_impact": s.expected_price_impact,
                    "cumulative_quantity": s.cumulative_quantity,
                    "remaining_quantity": s.remaining_quantity,
                }
                for s in self.slices
            ],
            "total_expected_cost": self.total_expected_cost,
            "expected_shortfall": self.expected_shortfall,
            "execution_risk": self.execution_risk,
            "urgency_parameter": self.urgency_parameter,
        }


class AlmgrenChrissOptimizer:
    """Almgren-Chriss optimal execution algorithm.

    The optimizer computes an optimal trade schedule that minimizes the
    trade-off between market impact and execution risk. It follows the
    classical Almgren-Chriss model with linear temporary and permanent
    impact functions.

    The objective function minimizes:
        E[cost] + lambda * Var[cost]

    where:
        - E[cost] includes permanent and temporary impact costs
        - Var[cost] represents the execution risk from price uncertainty
        - lambda is the risk aversion parameter

    Example:
        >>> params = OptimalExecutionParams(
        ...     total_quantity=10000,
        ...     duration_seconds=3600,
        ...     volatility=0.02,
        ...     temporary_impact=0.001,
        ...     permanent_impact=0.0001,
        ...     risk_aversion=1e-6,
        ... )
        >>> optimizer = AlmgrenChrissOptimizer(params)
        >>> result = optimizer.compute_schedule(num_slices=10)
        >>> len(result.slices)
        10
    """

    def __init__(self, params: OptimalExecutionParams) -> None:
        self._params = params
        self._kappa = self._compute_urgency_parameter()

    @property
    def params(self) -> OptimalExecutionParams:
        return self._params

    @property
    def urgency_parameter(self) -> float:
        """Kappa: controls the speed-risk trade-off."""
        return self._kappa

    def _compute_urgency_parameter(self) -> float:
        """Compute kappa (urgency parameter) from model inputs.

        kappa = sqrt(lambda * sigma^2 / eta)

        where:
            lambda = risk aversion
            sigma = volatility
            eta = temporary impact coefficient
        """
        p = self._params
        if p.temporary_impact <= 0:
            return 0.0

        # Scale volatility to the execution horizon
        # Annualized vol to per-second: sigma_sec = sigma_annual / sqrt(252 * 6.5 * 3600)
        seconds_per_year = 252 * 6.5 * 3600  # Trading seconds per year
        sigma_sec = p.volatility / math.sqrt(seconds_per_year)

        numerator = p.risk_aversion * sigma_sec * sigma_sec
        denominator = p.temporary_impact

        return math.sqrt(numerator / denominator)

    def _compute_trajectory(self, num_slices: int) -> np.ndarray:
        """Compute the optimal position trajectory.

        The optimal trajectory follows:
            x(t) = X * sinh(kappa * (T - t)) / sinh(kappa * T)

        where:
            X = total quantity
            T = total duration
            t = current time
            kappa = urgency parameter
        """
        p = self._params
        T = p.duration_seconds
        X = abs(p.total_quantity)
        kappa = self._kappa

        # Time points including start and end
        times = np.linspace(0, T, num_slices + 1)

        if kappa < 1e-10:
            # Linear trajectory for zero/negligible risk aversion
            trajectory = X * (T - times) / T
        else:
            # Almgren-Chriss optimal trajectory
            sinh_kT = np.sinh(kappa * T)
            if abs(sinh_kT) < 1e-12:
                trajectory = X * (T - times) / T
            else:
                trajectory = X * np.sinh(kappa * (T - times)) / sinh_kT

        # Ensure sign matches original quantity
        if p.total_quantity < 0:
            trajectory = -trajectory

        return trajectory

    def compute_schedule(self, num_slices: int) -> OptimalExecutionResult:
        """Compute the optimal execution schedule.

        Args:
            num_slices: Number of execution slices.

        Returns:
            OptimalExecutionResult containing the execution schedule and metrics.

        Raises:
            ValueError: If num_slices is not positive.
        """
        if num_slices <= 0:
            raise ValueError("num_slices must be positive")

        p = self._params
        T = p.duration_seconds
        X = p.total_quantity

        trajectory = self._compute_trajectory(num_slices)
        times = np.linspace(0, T, num_slices + 1)
        time_step = T / num_slices

        slices: List[ExecutionSlice] = []
        cumulative = 0.0

        for i in range(num_slices):
            # Quantity for this slice = position at t_i - position at t_{i+1}
            qty = trajectory[i] - trajectory[i + 1]

            # Expected temporary impact for this slice
            # Impact = eta * (trade rate)^2 = eta * (qty / dt)^2 * dt
            trade_rate = qty / time_step if time_step > 0 else 0.0
            temp_impact = p.temporary_impact * trade_rate * time_step

            cumulative += qty
            remaining = X - cumulative

            slices.append(
                ExecutionSlice(
                    time_offset=times[i],
                    quantity=qty,
                    expected_price_impact=temp_impact,
                    cumulative_quantity=cumulative,
                    remaining_quantity=remaining,
                )
            )

        # Compute total cost components
        expected_shortfall = self._compute_expected_shortfall(slices, time_step)
        execution_risk = self._compute_execution_risk(trajectory, time_step)
        total_cost = expected_shortfall + p.risk_aversion * execution_risk

        return OptimalExecutionResult(
            slices=tuple(slices),
            total_expected_cost=total_cost,
            expected_shortfall=expected_shortfall,
            execution_risk=execution_risk,
            urgency_parameter=self._kappa,
        )

    def _compute_expected_shortfall(
        self, slices: Sequence[ExecutionSlice], time_step: float
    ) -> float:
        """Compute expected implementation shortfall.

        E[S] = gamma * X^2 / 2 + sum_k eta * (n_k / tau)^2 * tau

        where:
            gamma = permanent impact
            X = total quantity
            eta = temporary impact
            n_k = quantity in slice k
            tau = time step
        """
        p = self._params
        X = abs(p.total_quantity)

        # Permanent impact cost (linear model)
        permanent_cost = p.permanent_impact * X * X / 2.0

        # Temporary impact cost
        temporary_cost = 0.0
        if time_step > 0:
            for s in slices:
                trade_rate = s.quantity / time_step
                temporary_cost += p.temporary_impact * trade_rate * trade_rate * time_step

        return permanent_cost + temporary_cost

    def _compute_execution_risk(self, trajectory: np.ndarray, time_step: float) -> float:
        """Compute variance of execution cost.

        Var[S] = sigma^2 * sum_k x_k^2 * tau

        where:
            sigma = volatility (scaled to execution horizon)
            x_k = remaining position at time k
            tau = time step
        """
        p = self._params

        # Scale volatility to per-second
        seconds_per_year = 252 * 6.5 * 3600
        sigma_sec = p.volatility / math.sqrt(seconds_per_year)

        # Sum of squared remaining positions (excluding final zero)
        # Use midpoint of each interval for better approximation
        variance = 0.0
        for i in range(len(trajectory) - 1):
            avg_position = (trajectory[i] + trajectory[i + 1]) / 2.0
            variance += sigma_sec * sigma_sec * avg_position * avg_position * time_step

        return variance


def compute_vwap_schedule(
    total_quantity: float,
    volume_profile: Sequence[float],
    duration_seconds: float,
) -> List[ExecutionSlice]:
    """Compute a VWAP-style execution schedule based on volume profile.

    This is a simpler alternative to Almgren-Chriss when historical volume
    profiles are available and market impact modeling is not required.

    Args:
        total_quantity: Total quantity to execute.
        volume_profile: Relative volume weights for each time bucket.
        duration_seconds: Total execution window in seconds.

    Returns:
        List of execution slices weighted by volume profile.

    Raises:
        ValueError: If inputs are invalid.
    """
    if not volume_profile:
        raise ValueError("volume_profile must not be empty")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")

    total_volume = sum(volume_profile)
    if total_volume <= 0:
        raise ValueError("volume_profile must sum to positive value")

    num_slices = len(volume_profile)
    time_step = duration_seconds / num_slices
    weights = [v / total_volume for v in volume_profile]

    slices: List[ExecutionSlice] = []
    cumulative = 0.0

    for i, weight in enumerate(weights):
        qty = total_quantity * weight
        cumulative += qty

        slices.append(
            ExecutionSlice(
                time_offset=i * time_step,
                quantity=qty,
                expected_price_impact=0.0,  # VWAP doesn't model impact
                cumulative_quantity=cumulative,
                remaining_quantity=total_quantity - cumulative,
            )
        )

    return slices


__all__ = [
    "AlmgrenChrissOptimizer",
    "ExecutionSlice",
    "OptimalExecutionParams",
    "OptimalExecutionResult",
    "compute_vwap_schedule",
]
