# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Port definitions (interfaces) for FPM-A hexagonal architecture.

This module defines abstract interfaces (ports) that establish contracts between
FPM-A core logic and external adapters. Using Python's Protocol typing, ports
enable structural subtyping without explicit inheritance.

Ports represent the boundaries of the FPM-A domain. Core business logic depends
only on these abstractions, never on concrete implementations. This design
supports testing, modularity, and infrastructure flexibility.

Available Ports:
    SumPort: Basic arithmetic interface (backward compatibility)
    DataRetrievalPort: Market data access interface
    RiskModelPort: Risk computation interface
    OptimizationPort: Portfolio optimization solver interface
    PersistencePort: State storage and retrieval interface
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Protocol, Sequence

import numpy as np
import pandas as pd


class SumPort(Protocol):
    """Basic arithmetic interface for backward compatibility."""

    def sum(self, a: int, b: int) -> int:
        """Compute sum of two integers."""
        ...


class DataRetrievalPort(Protocol):
    """Interface for retrieving market data.

    Implementations may fetch data from databases, APIs, or files.
    """

    def get_returns(
        self,
        symbols: Sequence[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Retrieve returns data for specified symbols and date range.

        Args:
            symbols: List of asset symbols
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)

        Returns:
            DataFrame with symbols as columns and dates as index
        """
        ...

    def get_prices(
        self,
        symbols: Sequence[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Retrieve price data for specified symbols and date range.

        Args:
            symbols: List of asset symbols
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)

        Returns:
            DataFrame with symbols as columns and dates as index
        """
        ...

    def get_fundamentals(
        self,
        symbols: Sequence[str],
        metrics: Sequence[str],
    ) -> Dict[str, Dict[str, float]]:
        """Retrieve fundamental metrics for specified symbols.

        Args:
            symbols: List of asset symbols
            metrics: List of metric names to retrieve

        Returns:
            Nested dict mapping symbol -> metric -> value
        """
        ...


class RiskModelPort(Protocol):
    """Interface for risk model computations.

    Implementations provide various risk metrics and factor decompositions.
    """

    def compute_covariance(
        self,
        returns: pd.DataFrame,
        method: str = "sample",
    ) -> np.ndarray:
        """Compute covariance matrix from returns.

        Args:
            returns: DataFrame of asset returns
            method: Estimation method ('sample', 'shrinkage', 'factor')

        Returns:
            Covariance matrix as numpy array
        """
        ...

    def compute_var(
        self,
        weights: np.ndarray,
        returns: pd.DataFrame,
        confidence: float = 0.95,
    ) -> float:
        """Compute Value at Risk for portfolio.

        Args:
            weights: Portfolio weight vector
            returns: DataFrame of asset returns
            confidence: Confidence level (0-1)

        Returns:
            VaR estimate
        """
        ...

    def compute_cvar(
        self,
        weights: np.ndarray,
        returns: pd.DataFrame,
        confidence: float = 0.95,
    ) -> float:
        """Compute Conditional Value at Risk (Expected Shortfall).

        Args:
            weights: Portfolio weight vector
            returns: DataFrame of asset returns
            confidence: Confidence level (0-1)

        Returns:
            CVaR estimate
        """
        ...

    def factor_decomposition(
        self,
        returns: pd.DataFrame,
        n_factors: int = 3,
    ) -> Dict[str, Any]:
        """Decompose returns into factor exposures.

        Args:
            returns: DataFrame of asset returns
            n_factors: Number of factors to extract

        Returns:
            Dictionary with factor loadings and residual variance
        """
        ...


class OptimizationPort(Protocol):
    """Interface for portfolio optimization solvers.

    Implementations solve various portfolio optimization problems.
    """

    def mean_variance_optimize(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        constraints: Mapping[str, Any] | None = None,
    ) -> np.ndarray:
        """Solve mean-variance optimization.

        Args:
            expected_returns: Expected return vector
            covariance: Covariance matrix
            constraints: Optional optimization constraints

        Returns:
            Optimal weight vector
        """
        ...

    def risk_parity_optimize(
        self,
        covariance: np.ndarray,
        risk_budget: np.ndarray | None = None,
    ) -> np.ndarray:
        """Solve risk parity optimization.

        Args:
            covariance: Covariance matrix
            risk_budget: Optional risk budget per asset (default: equal)

        Returns:
            Risk parity weight vector
        """
        ...

    def black_litterman(
        self,
        market_weights: np.ndarray,
        covariance: np.ndarray,
        views: Dict[str, float],
        view_confidence: np.ndarray,
    ) -> np.ndarray:
        """Apply Black-Litterman model for views incorporation.

        Args:
            market_weights: Market capitalization weights
            covariance: Covariance matrix
            views: Expected return views
            view_confidence: Confidence in each view

        Returns:
            Posterior expected returns
        """
        ...


class PersistencePort(Protocol):
    """Interface for state persistence.

    Implementations handle storage and retrieval of portfolio state.
    """

    def save_portfolio_state(
        self,
        portfolio_id: str,
        weights: Dict[str, float],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Persist current portfolio state.

        Args:
            portfolio_id: Unique portfolio identifier
            weights: Current portfolio weights
            metadata: Optional metadata to store
        """
        ...

    def load_portfolio_state(
        self,
        portfolio_id: str,
    ) -> Dict[str, Any] | None:
        """Load previously saved portfolio state.

        Args:
            portfolio_id: Unique portfolio identifier

        Returns:
            Portfolio state dict or None if not found
        """
        ...

    def save_regime_history(
        self,
        portfolio_id: str,
        history: Sequence[Mapping[str, Any]],
    ) -> None:
        """Persist regime detection history.

        Args:
            portfolio_id: Unique portfolio identifier
            history: List of regime snapshots
        """
        ...

    def load_regime_history(
        self,
        portfolio_id: str,
    ) -> Sequence[Dict[str, Any]]:
        """Load regime detection history.

        Args:
            portfolio_id: Unique portfolio identifier

        Returns:
            List of regime snapshot dicts
        """
        ...


__all__ = [
    "SumPort",
    "DataRetrievalPort",
    "RiskModelPort",
    "OptimizationPort",
    "PersistencePort",
]
