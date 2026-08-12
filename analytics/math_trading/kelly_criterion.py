# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Extended Kelly Criterion for multi-asset position sizing.

This module implements the Kelly Criterion for optimal position sizing,
extended to handle multiple correlated assets and risk constraints.

Mathematical contract
=====================
* Inputs are expressed in *decimal* returns (e.g., 0.05 = 5%).
* Covariance matrices must be symmetric positive semi-definite (PSD) to
  ensure ``f^T Σ f ≥ 0`` for any position vector ``f``. Singular matrices
  are allowed but will be handled with a pseudo-inverse when needed.
* Position limits are enforced through ``max_position`` (per-asset cap) and
  ``max_leverage`` (L1 norm of positions); infeasible or non-finite inputs
  are rejected before optimization.

The Kelly Criterion maximizes expected log utility:
    max E[log(1 + r_p)]

For a single asset with return r and probability p:
    f* = p - (1-p)/b = (b*p - q) / b

where:
    f* = optimal fraction of capital
    p = probability of winning
    q = 1-p = probability of losing
    b = win/loss ratio (reward/risk)

For multiple assets, the optimal allocation solves:
    f* = Sigma^{-1} * mu

subject to risk constraints and position limits.

References:
    Kelly, J.L. (1956). "A New Interpretation of Information Rate."
    Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import numpy.typing as npt
from scipy.optimize import Bounds, minimize

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KellyParams:
    """Parameters for single-asset Kelly criterion.

    Attributes:
        win_probability: Probability of winning trade (0 < p < 1).
        win_loss_ratio: Ratio of average win to average loss (b > 0).
        max_fraction: Maximum position as fraction of capital.
        fractional_kelly: Kelly fraction to use (0.5 = half Kelly).
    """

    win_probability: float
    win_loss_ratio: float
    max_fraction: float = 1.0
    fractional_kelly: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.win_probability < 1:
            raise ValueError("win_probability must be between 0 and 1")
        if self.win_loss_ratio <= 0:
            raise ValueError("win_loss_ratio must be positive")
        if self.max_fraction <= 0:
            raise ValueError("max_fraction must be positive")
        if not 0 < self.fractional_kelly <= 1:
            raise ValueError("fractional_kelly must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class KellyResult:
    """Result of Kelly criterion computation.

    Attributes:
        optimal_fraction: Optimal fraction of capital to bet.
        full_kelly: Full Kelly fraction (before fractional adjustment).
        edge: Expected edge (expected return per unit bet).
        growth_rate: Expected log growth rate.
        max_drawdown_estimate: Estimated maximum drawdown at this fraction.
    """

    optimal_fraction: float
    full_kelly: float
    edge: float
    growth_rate: float
    max_drawdown_estimate: float

    def to_dict(self) -> dict:
        return {
            "optimal_fraction": self.optimal_fraction,
            "full_kelly": self.full_kelly,
            "edge": self.edge,
            "growth_rate": self.growth_rate,
            "max_drawdown_estimate": self.max_drawdown_estimate,
        }


class KellyCriterion:
    """Single-asset Kelly Criterion calculator.

    The Kelly Criterion determines the optimal fraction of capital to
    risk on a bet given the probability of winning and the payoff ratio.

    Example:
        >>> kelly = KellyCriterion()
        >>> params = KellyParams(win_probability=0.6, win_loss_ratio=1.5)
        >>> result = kelly.compute(params)
        >>> result.optimal_fraction
        0.333...
    """

    def compute(self, params: KellyParams) -> KellyResult:
        """Compute optimal Kelly fraction.

        Args:
            params: Kelly parameters including probabilities and ratios.

        Returns:
            KellyResult with optimal fraction and related metrics.
        """
        p = params.win_probability
        q = 1 - p
        b = params.win_loss_ratio

        # Full Kelly formula: f* = (b*p - q) / b
        full_kelly = (b * p - q) / b

        # Edge: expected return per unit bet
        edge = p * b - q

        # Apply fractional Kelly and constraints
        optimal = full_kelly * params.fractional_kelly
        optimal = max(0.0, min(optimal, params.max_fraction))

        # Expected log growth rate: g = p * log(1 + f*b) + q * log(1 - f)
        eps = 1e-12
        if optimal > 0 and optimal < 1:
            log_gain = np.log(np.clip(1 + optimal * b, eps, None))
            log_loss = np.log(np.clip(1 - optimal, eps, None))
            growth_rate = p * log_gain + q * log_loss
        else:
            growth_rate = 0.0

        # Maximum drawdown estimate (approximate)
        # For continuous betting, max_dd ≈ f / (1 + f) for high number of bets
        if optimal > 0:
            max_dd = 2 * optimal / (1 + optimal)
        else:
            max_dd = 0.0

        return KellyResult(
            optimal_fraction=optimal,
            full_kelly=full_kelly,
            edge=edge,
            growth_rate=growth_rate,
            max_drawdown_estimate=max_dd,
        )


@dataclass(frozen=True, slots=True)
class MultiAssetKellyParams:
    """Parameters for multi-asset Kelly optimization.

    Attributes:
        expected_returns: Expected return for each asset.
        covariance_matrix: Covariance matrix of asset returns.
        asset_names: Ordered asset identifiers.
        max_position: Maximum position per asset.
        max_leverage: Maximum total leverage (sum of absolute positions).
        fractional_kelly: Kelly fraction to use (0.5 = half Kelly).
        risk_free_rate: Risk-free rate for excess returns.
    """

    expected_returns: np.ndarray
    covariance_matrix: np.ndarray
    asset_names: tuple[str, ...]
    max_position: float = 1.0
    max_leverage: float = 2.0
    fractional_kelly: float = 0.5
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        n = len(self.asset_names)
        if not np.isfinite(self.max_position) or not np.isfinite(self.max_leverage):
            raise ValueError("max_position and max_leverage must be finite")
        if self.expected_returns.shape != (n,):
            raise ValueError("expected_returns dimension mismatch")
        if self.covariance_matrix.shape != (n, n):
            raise ValueError("covariance_matrix dimension mismatch")
        if not np.all(np.isfinite(self.expected_returns)):
            raise ValueError("expected_returns must be finite")
        if not np.all(np.isfinite(self.covariance_matrix)):
            raise ValueError("covariance_matrix must be finite")
        if not np.isfinite(self.risk_free_rate):
            raise ValueError("risk_free_rate must be finite")
        if self.max_position <= 0:
            raise ValueError("max_position must be positive")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        if not 0 < self.fractional_kelly <= 1:
            raise ValueError("fractional_kelly must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class MultiAssetKellyResult:
    """Result of multi-asset Kelly optimization.

    Attributes:
        optimal_positions: Optimal fraction for each asset.
        full_kelly_positions: Full Kelly positions (before constraints).
        expected_return: Portfolio expected return.
        portfolio_variance: Portfolio variance.
        sharpe_ratio: Portfolio Sharpe ratio.
        leverage: Total leverage used.
        growth_rate: Expected log growth rate.
    """

    optimal_positions: Mapping[str, float]
    full_kelly_positions: Mapping[str, float]
    expected_return: float
    portfolio_variance: float
    sharpe_ratio: float
    leverage: float
    growth_rate: float

    def to_dict(self) -> dict:
        return {
            "optimal_positions": dict(self.optimal_positions),
            "full_kelly_positions": dict(self.full_kelly_positions),
            "expected_return": self.expected_return,
            "portfolio_variance": self.portfolio_variance,
            "sharpe_ratio": self.sharpe_ratio,
            "leverage": self.leverage,
            "growth_rate": self.growth_rate,
        }


class MultiAssetKelly:
    """Multi-asset Kelly Criterion optimizer.

    Extends the Kelly Criterion to multiple correlated assets by
    maximizing expected log utility subject to position constraints.

    The unconstrained solution is:
        f* = Sigma^{-1} * (mu - r_f)

    where:
        Sigma = covariance matrix
        mu = expected returns
        r_f = risk-free rate

    Example:
        >>> import numpy as np
        >>> mu = np.array([0.10, 0.08, 0.12])
        >>> sigma = np.array([
        ...     [0.04, 0.01, 0.02],
        ...     [0.01, 0.03, 0.01],
        ...     [0.02, 0.01, 0.05]
        ... ])
        >>> params = MultiAssetKellyParams(
        ...     expected_returns=mu,
        ...     covariance_matrix=sigma,
        ...     asset_names=("AAPL", "GOOG", "MSFT"),
        ... )
        >>> kelly = MultiAssetKelly()
        >>> result = kelly.optimize(params)
    """

    _EIGEN_ATOL = 1e-12

    @staticmethod
    def _validate_covariance(matrix: npt.NDArray[np.float64]) -> None:
        if not np.allclose(matrix, matrix.T, atol=MultiAssetKelly._EIGEN_ATOL):
            raise ValueError("covariance_matrix must be symmetric")

        eigenvalues = np.linalg.eigvalsh(matrix)
        if np.any(eigenvalues < -MultiAssetKelly._EIGEN_ATOL):
            raise ValueError("covariance_matrix must be positive semi-definite")

    @staticmethod
    def _solve_covariance(
        covariance: npt.NDArray[np.float64],
        expected_excess: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        MultiAssetKelly._validate_covariance(covariance)

        condition_number = np.linalg.cond(covariance)
        try:
            if condition_number < 1e8:
                return np.linalg.solve(covariance, expected_excess)
        except np.linalg.LinAlgError:
            condition_number = np.inf

        logger.warning(
            "Covariance matrix ill-conditioned (cond=%.2e); using pseudo-inverse",
            condition_number,
        )
        pseudo_inverse = np.linalg.pinv(covariance)
        return pseudo_inverse @ expected_excess

    def optimize(self, params: MultiAssetKellyParams) -> MultiAssetKellyResult:
        """Compute optimal multi-asset Kelly allocation.

        Args:
            params: Multi-asset Kelly parameters.

        Returns:
            MultiAssetKellyResult with optimal allocations and metrics.
        """
        n = len(params.asset_names)
        mu = params.expected_returns - params.risk_free_rate
        sigma = params.covariance_matrix

        # Compute unconstrained full Kelly
        full_kelly = self._solve_covariance(sigma, mu)
        if not np.all(np.isfinite(full_kelly)):
            raise ValueError("Computed Kelly solution contains non-finite values")

        # Store full Kelly positions
        full_kelly_dict = {params.asset_names[i]: full_kelly[i] for i in range(n)}

        # Apply fractional Kelly
        scaled_kelly = full_kelly * params.fractional_kelly

        # Optimize with constraints
        def neg_log_utility(f: np.ndarray) -> float:
            """Negative expected log utility (for minimization)."""
            port_return = f @ mu
            port_var = f @ sigma @ f

            if port_var < -self._EIGEN_ATOL:
                return 1e10

            port_var = max(float(port_var), 0.0)

            # Log utility approximation: log(1 + r) ≈ r - r^2/2
            # E[log(1 + r_p)] ≈ E[r_p] - Var[r_p]/2
            log_utility = port_return - 0.5 * port_var
            return -log_utility

        def utility_grad(f: np.ndarray) -> np.ndarray:
            """Gradient of negative log utility."""
            return -(mu - sigma @ f)

        # Bounds: position limits
        lb = -params.max_position * np.ones(n)
        ub = params.max_position * np.ones(n)
        bounds = Bounds(lb, ub)

        # Leverage constraint: sum(|f_i|) <= max_leverage
        # This is non-linear, so we use a soft constraint via penalty
        def leverage_constraint(f: np.ndarray) -> float:
            return params.max_leverage - np.sum(np.abs(f))

        constraints = [{"type": "ineq", "fun": leverage_constraint}]

        # Initial guess: scaled Kelly or zero
        x0 = np.clip(scaled_kelly, -params.max_position, params.max_position)
        if np.sum(np.abs(x0)) > params.max_leverage:
            x0 = x0 * params.max_leverage / np.sum(np.abs(x0))

        if not np.all(np.isfinite(x0)):
            raise ValueError("Initial guess contains non-finite values")

        result = minimize(
            neg_log_utility,
            x0,
            method="SLSQP",
            jac=utility_grad,
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-9},
        )

        f_optimal = result.x

        leverage = float(np.sum(np.abs(f_optimal)))
        if leverage > params.max_leverage + 1e-9:
            f_optimal = f_optimal * params.max_leverage / leverage
            leverage = float(np.sum(np.abs(f_optimal)))

        # Compute metrics
        port_return = float(f_optimal @ mu) + params.risk_free_rate
        port_var = float(f_optimal @ sigma @ f_optimal)
        if port_var < 0 and port_var > -self._EIGEN_ATOL:
            port_var = 0.0
        port_var = max(port_var, 0.0)
        port_std = np.sqrt(port_var) if port_var > 0 else 0.0

        sharpe = (port_return - params.risk_free_rate) / port_std if port_std > 0 else 0.0

        # Growth rate approximation
        if port_var > 0:
            growth_rate = port_return - 0.5 * port_var
        else:
            growth_rate = port_return

        optimal_dict = {params.asset_names[i]: f_optimal[i] for i in range(n)}

        return MultiAssetKellyResult(
            optimal_positions=optimal_dict,
            full_kelly_positions=full_kelly_dict,
            expected_return=port_return,
            portfolio_variance=port_var,
            sharpe_ratio=sharpe,
            leverage=leverage,
            growth_rate=growth_rate,
        )

    def compute_from_historical(
        self,
        returns: np.ndarray,
        asset_names: Sequence[str],
        lookback: int | None = None,
        fractional_kelly: float = 0.5,
        max_position: float = 1.0,
        max_leverage: float = 2.0,
    ) -> MultiAssetKellyResult:
        """Compute Kelly allocation from historical returns.

        Args:
            returns: Historical returns matrix (periods x assets).
            asset_names: Asset identifiers.
            lookback: Number of periods to use (None = all).
            fractional_kelly: Kelly fraction to use.
            max_position: Maximum position per asset.
            max_leverage: Maximum total leverage.

        Returns:
            MultiAssetKellyResult with optimal allocations.
        """
        if lookback is not None:
            returns = returns[-lookback:]

        if not np.all(np.isfinite(returns)):
            raise ValueError("returns must be finite for Kelly computation")

        mu = np.mean(returns, axis=0)
        sigma = np.cov(returns, rowvar=False)

        # Ensure sigma is 2D
        if sigma.ndim == 0:
            sigma = np.array([[sigma]])

        params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=tuple(asset_names),
            max_position=max_position,
            max_leverage=max_leverage,
            fractional_kelly=fractional_kelly,
        )

        return self.optimize(params)


def kelly_from_edge_variance(
    edge: float,
    variance: float,
    fractional_kelly: float = 0.5,
    max_fraction: float = 1.0,
) -> float:
    """Compute Kelly fraction from edge and variance.

    For continuous returns with edge E[r] and variance Var[r]:
        f* = edge / variance

    Args:
        edge: Expected excess return.
        variance: Return variance.
        fractional_kelly: Kelly fraction to apply.
        max_fraction: Maximum position limit.

    Returns:
        Optimal position fraction.
    """
    if variance <= 0:
        return 0.0

    full_kelly = edge / variance
    optimal = full_kelly * fractional_kelly
    return max(0.0, min(optimal, max_fraction))


__all__ = [
    "KellyCriterion",
    "KellyParams",
    "KellyResult",
    "MultiAssetKelly",
    "MultiAssetKellyParams",
    "MultiAssetKellyResult",
    "kelly_from_edge_variance",
]
