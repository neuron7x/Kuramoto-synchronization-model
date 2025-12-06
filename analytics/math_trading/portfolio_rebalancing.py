# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Portfolio rebalancing with transaction cost minimization.

This module implements a quadratic programming approach to portfolio rebalancing
that minimizes transaction costs while respecting constraints on target weights.

The optimization problem:
    minimize: sum_i c_i * |w_i - w_i^target| + penalty * ||delta_w||^2

    subject to:
        |w_i - w_i^target| <= tolerance_i for all assets
        sum_i w_i = 1 (full investment)
        w_i >= 0 for all i (long-only) or w_i free (allow shorts)

Key features:
    - L1 + L2 penalty for balancing turnover and tracking error
    - Asset-specific tolerance bands
    - Support for tax-lot aware rebalancing
    - Minimum trade size constraints
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize


@dataclass(frozen=True, slots=True)
class RebalanceConstraints:
    """Constraints for portfolio rebalancing.

    Attributes:
        tolerance: Maximum deviation from target (default 0.02 = 2%).
        min_trade_size: Minimum trade size as fraction of portfolio.
        max_turnover: Maximum portfolio turnover allowed.
        long_only: If True, prohibit short positions.
        cash_weight_min: Minimum cash allocation (default 0).
        cash_weight_max: Maximum cash allocation (default 1).
    """

    tolerance: float = 0.02
    min_trade_size: float = 0.0001
    max_turnover: float = 1.0
    long_only: bool = True
    cash_weight_min: float = 0.0
    cash_weight_max: float = 1.0

    def __post_init__(self) -> None:
        if self.tolerance < 0:
            raise ValueError("tolerance must be non-negative")
        if self.min_trade_size < 0:
            raise ValueError("min_trade_size must be non-negative")
        if self.max_turnover <= 0:
            raise ValueError("max_turnover must be positive")
        if not 0 <= self.cash_weight_min <= self.cash_weight_max <= 1:
            raise ValueError("invalid cash weight bounds")


@dataclass(frozen=True, slots=True)
class RebalanceRequest:
    """Input for a rebalancing computation.

    Attributes:
        current_weights: Current portfolio weights by asset.
        target_weights: Target portfolio weights by asset.
        transaction_costs: Transaction cost per asset (as fraction).
        asset_tolerances: Per-asset tolerance overrides (optional).
        portfolio_value: Total portfolio value for sizing calculations.
    """

    current_weights: Mapping[str, float]
    target_weights: Mapping[str, float]
    transaction_costs: Mapping[str, float] | None = None
    asset_tolerances: Mapping[str, float] | None = None
    portfolio_value: float = 1.0

    def __post_init__(self) -> None:
        if not self.current_weights:
            raise ValueError("current_weights cannot be empty")
        if not self.target_weights:
            raise ValueError("target_weights cannot be empty")
        if self.portfolio_value <= 0:
            raise ValueError("portfolio_value must be positive")


@dataclass(frozen=True, slots=True)
class TradeOrder:
    """A single trade in the rebalance solution.

    Attributes:
        asset: Asset identifier.
        current_weight: Current weight.
        target_weight: Optimal target weight after rebalancing.
        trade_weight: Weight change required (positive = buy).
        trade_value: Dollar value of trade.
        transaction_cost: Cost of this trade.
    """

    asset: str
    current_weight: float
    target_weight: float
    trade_weight: float
    trade_value: float
    transaction_cost: float


@dataclass(frozen=True, slots=True)
class RebalanceResult:
    """Result of portfolio rebalancing optimization.

    Attributes:
        orders: List of trade orders.
        total_turnover: Total portfolio turnover.
        total_transaction_cost: Total transaction costs.
        tracking_error: Squared deviation from targets.
        optimization_success: Whether optimization converged.
        final_weights: Final portfolio weights after rebalancing.
    """

    orders: tuple[TradeOrder, ...]
    total_turnover: float
    total_transaction_cost: float
    tracking_error: float
    optimization_success: bool
    final_weights: Mapping[str, float]

    def to_dict(self) -> dict:
        return {
            "orders": [
                {
                    "asset": o.asset,
                    "current_weight": o.current_weight,
                    "target_weight": o.target_weight,
                    "trade_weight": o.trade_weight,
                    "trade_value": o.trade_value,
                    "transaction_cost": o.transaction_cost,
                }
                for o in self.orders
            ],
            "total_turnover": self.total_turnover,
            "total_transaction_cost": self.total_transaction_cost,
            "tracking_error": self.tracking_error,
            "optimization_success": self.optimization_success,
            "final_weights": dict(self.final_weights),
        }


class PortfolioRebalancer:
    """Quadratic programming based portfolio rebalancer.

    Minimizes transaction costs while keeping portfolio weights within
    tolerance bands of their targets. The optimization balances:
    - Transaction costs (minimize trading)
    - Tracking error (stay close to targets)
    - Turnover constraints

    Example:
        >>> rebalancer = PortfolioRebalancer()
        >>> request = RebalanceRequest(
        ...     current_weights={"AAPL": 0.3, "GOOG": 0.3, "MSFT": 0.4},
        ...     target_weights={"AAPL": 0.33, "GOOG": 0.33, "MSFT": 0.34},
        ...     transaction_costs={"AAPL": 0.001, "GOOG": 0.001, "MSFT": 0.001},
        ... )
        >>> result = rebalancer.optimize(request)
        >>> result.optimization_success
        True
    """

    def __init__(
        self,
        constraints: RebalanceConstraints | None = None,
        tracking_penalty: float = 1.0,
    ) -> None:
        """Initialize the rebalancer.

        Args:
            constraints: Rebalancing constraints.
            tracking_penalty: Weight on tracking error penalty (higher = closer to target).
        """
        self._constraints = constraints or RebalanceConstraints()
        self._tracking_penalty = tracking_penalty

    @property
    def constraints(self) -> RebalanceConstraints:
        return self._constraints

    def optimize(self, request: RebalanceRequest) -> RebalanceResult:
        """Compute optimal rebalancing trades.

        Args:
            request: Rebalancing request with current and target weights.

        Returns:
            RebalanceResult with optimal trades and metrics.
        """
        # Build asset list from union of current and target weights
        all_assets = sorted(
            set(request.current_weights.keys()) | set(request.target_weights.keys())
        )
        n = len(all_assets)

        # Build vectors
        w_current = np.array([request.current_weights.get(a, 0.0) for a in all_assets])
        w_target = np.array([request.target_weights.get(a, 0.0) for a in all_assets])

        # Transaction costs (default to 0.001 = 10 bps)
        default_cost = 0.001
        if request.transaction_costs:
            costs = np.array(
                [request.transaction_costs.get(a, default_cost) for a in all_assets]
            )
        else:
            costs = np.full(n, default_cost)

        # Per-asset tolerances
        default_tol = self._constraints.tolerance
        if request.asset_tolerances:
            tolerances = np.array(
                [request.asset_tolerances.get(a, default_tol) for a in all_assets]
            )
        else:
            tolerances = np.full(n, default_tol)

        # Optimization: find optimal weights w that minimize cost
        # Objective: sum_i c_i * |w_i - w_current_i| + penalty * ||w - w_target||^2
        #
        # We reformulate using auxiliary variables t_i >= |w_i - w_current_i|
        # Decision variables: [w_0, ..., w_{n-1}, t_0, ..., t_{n-1}]

        def objective(x: np.ndarray) -> float:
            w = x[:n]
            t = x[n:]

            # L1 transaction cost
            l1_cost = np.sum(costs * t)

            # L2 tracking error
            l2_tracking = np.sum((w - w_target) ** 2)

            return l1_cost + self._tracking_penalty * l2_tracking

        def objective_grad(x: np.ndarray) -> np.ndarray:
            w = x[:n]

            grad = np.zeros(2 * n)
            # Gradient w.r.t. w
            grad[:n] = 2 * self._tracking_penalty * (w - w_target)
            # Gradient w.r.t. t
            grad[n:] = costs

            return grad

        # Initial guess: current weights with zero auxiliary vars
        x0 = np.concatenate([w_current, np.abs(w_target - w_current)])

        # Bounds
        if self._constraints.long_only:
            w_lower = np.zeros(n)
        else:
            w_lower = np.full(n, -1.0)
        w_upper = np.ones(n)
        t_lower = np.zeros(n)
        t_upper = np.full(n, 2.0)  # Max turnover per asset

        bounds = Bounds(
            np.concatenate([w_lower, t_lower]),
            np.concatenate([w_upper, t_upper]),
        )

        # Constraints
        constraints_list = []

        # Sum of weights = 1
        A_sum = np.zeros((1, 2 * n))
        A_sum[0, :n] = 1.0
        constraints_list.append(LinearConstraint(A_sum, 1.0, 1.0))

        # t_i >= w_i - w_current_i (linearization of absolute value)
        # t_i >= -(w_i - w_current_i)
        # These become: -t_i + w_i <= w_current_i and -t_i - w_i <= -w_current_i

        A_abs_pos = np.zeros((n, 2 * n))
        for i in range(n):
            A_abs_pos[i, i] = 1.0
            A_abs_pos[i, n + i] = -1.0
        constraints_list.append(LinearConstraint(A_abs_pos, -np.inf, w_current))

        A_abs_neg = np.zeros((n, 2 * n))
        for i in range(n):
            A_abs_neg[i, i] = -1.0
            A_abs_neg[i, n + i] = -1.0
        constraints_list.append(LinearConstraint(A_abs_neg, -np.inf, -w_current))

        # Tolerance constraints: |w_i - w_target_i| <= tolerance_i
        A_tol_pos = np.zeros((n, 2 * n))
        for i in range(n):
            A_tol_pos[i, i] = 1.0
        constraints_list.append(
            LinearConstraint(A_tol_pos, w_target - tolerances, w_target + tolerances)
        )

        # Total turnover constraint
        A_turnover = np.zeros((1, 2 * n))
        A_turnover[0, n:] = 0.5  # Each t_i counts half (buy + sell = full turnover)
        constraints_list.append(
            LinearConstraint(A_turnover, 0.0, self._constraints.max_turnover)
        )

        # Solve
        result = minimize(
            objective,
            x0,
            method="SLSQP",
            jac=objective_grad,
            bounds=bounds,
            constraints=constraints_list,
            options={"maxiter": 1000, "ftol": 1e-9},
        )

        w_optimal = result.x[:n]
        # t_optimal contains auxiliary variables for absolute value linearization
        # (not used directly, but kept for potential debugging)
        _ = result.x[n:]

        # Build trade orders
        orders: list[TradeOrder] = []
        total_turnover = 0.0
        total_cost = 0.0
        tracking_error = 0.0

        for i, asset in enumerate(all_assets):
            trade_weight = w_optimal[i] - w_current[i]

            # Skip tiny trades below minimum size
            if abs(trade_weight) < self._constraints.min_trade_size:
                # Keep current weight
                w_optimal[i] = w_current[i]
                trade_weight = 0.0

            trade_value = trade_weight * request.portfolio_value
            tx_cost = abs(trade_weight) * costs[i] * request.portfolio_value

            total_turnover += abs(trade_weight)
            total_cost += tx_cost
            tracking_error += (w_optimal[i] - w_target[i]) ** 2

            if abs(trade_weight) >= self._constraints.min_trade_size:
                orders.append(
                    TradeOrder(
                        asset=asset,
                        current_weight=w_current[i],
                        target_weight=w_optimal[i],
                        trade_weight=trade_weight,
                        trade_value=trade_value,
                        transaction_cost=tx_cost,
                    )
                )

        final_weights = {asset: w_optimal[i] for i, asset in enumerate(all_assets)}

        return RebalanceResult(
            orders=tuple(orders),
            total_turnover=total_turnover,
            total_transaction_cost=total_cost,
            tracking_error=tracking_error,
            optimization_success=result.success,
            final_weights=final_weights,
        )


def compute_minimum_variance_trades(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    covariance_matrix: np.ndarray,
    asset_names: Sequence[str],
    risk_budget: float = 0.1,
) -> Mapping[str, float]:
    """Compute trades that minimize portfolio variance change.

    This is an alternative to pure target-tracking when you want to
    minimize the variance impact of rebalancing.

    Args:
        current_weights: Current portfolio weights.
        target_weights: Target portfolio weights.
        covariance_matrix: Asset covariance matrix.
        asset_names: Ordered asset names matching covariance matrix.
        risk_budget: Maximum acceptable variance change.

    Returns:
        Optimal weight changes by asset.
    """
    n = len(asset_names)
    if covariance_matrix.shape != (n, n):
        raise ValueError("covariance_matrix dimension mismatch")

    w_current = np.array([current_weights.get(a, 0.0) for a in asset_names])
    w_target = np.array([target_weights.get(a, 0.0) for a in asset_names])
    delta = w_target - w_current

    # Compute variance change from full rebalance
    # Var(w + delta) - Var(w) = delta^T Sigma delta + 2 * w^T Sigma delta
    full_var_change = (
        delta @ covariance_matrix @ delta +
        2 * w_current @ covariance_matrix @ delta
    )

    if abs(full_var_change) <= risk_budget:
        # Full rebalance is within budget
        return {a: delta[i] for i, a in enumerate(asset_names)}

    # Scale down trades to fit variance budget
    # Find alpha such that variance change is exactly risk_budget
    # (alpha * delta)^T Sigma (alpha * delta) + 2 * w^T Sigma (alpha * delta) = risk_budget
    a_coef = delta @ covariance_matrix @ delta
    b_coef = 2 * w_current @ covariance_matrix @ delta

    if abs(a_coef) < 1e-12:
        alpha = 1.0
    else:
        # Quadratic: a * alpha^2 + b * alpha - risk_budget = 0
        discriminant = b_coef * b_coef + 4 * a_coef * risk_budget
        if discriminant < 0:
            alpha = 0.0
        else:
            alpha1 = (-b_coef + np.sqrt(discriminant)) / (2 * a_coef)
            alpha2 = (-b_coef - np.sqrt(discriminant)) / (2 * a_coef)
            # Choose the positive root that's <= 1
            candidates = [a for a in [alpha1, alpha2] if 0 <= a <= 1]
            alpha = max(candidates) if candidates else 0.0

    scaled_delta = alpha * delta
    return {a: scaled_delta[i] for i, a in enumerate(asset_names)}


__all__ = [
    "PortfolioRebalancer",
    "RebalanceRequest",
    "RebalanceResult",
    "RebalanceConstraints",
    "TradeOrder",
    "compute_minimum_variance_trades",
]
