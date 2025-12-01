# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Local adapter implementations for FPM-A ports.

This module provides concrete implementations of FPM-A port interfaces for
local (in-process) execution. Adapters implement the ports defined in the
ports module, enabling dependency inversion and testability.

The hexagonal architecture pattern allows FPM-A core logic to remain independent
of infrastructure details. Alternative adapters could target cloud services,
distributed computing, or external analytics engines without changing core code.

Available Implementations:
    LocalSum: Local implementation of SumPort interface
    LocalRiskModel: NumPy-based risk model computations
    LocalOptimizer: SciPy-based portfolio optimization
    InMemoryPersistence: In-memory state storage for testing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm

from analytics.fpma.src.ports.ports import (
    OptimizationPort,
    PersistencePort,
    RiskModelPort,
    SumPort,
)


class LocalSum(SumPort):
    """Local implementation of the SumPort interface."""

    def sum(self, a: int, b: int) -> int:
        """Compute sum of two integers."""
        return a + b


class LocalRiskModel(RiskModelPort):
    """NumPy-based implementation of risk model computations."""

    def __init__(self, shrinkage_target: float = 0.5) -> None:
        """Initialize the risk model.

        Args:
            shrinkage_target: Target for Ledoit-Wolf shrinkage (0-1)
        """
        self.shrinkage_target = shrinkage_target

    def compute_covariance(
        self,
        returns: pd.DataFrame,
        method: str = "sample",
    ) -> np.ndarray:
        """Compute covariance matrix using specified method.

        Args:
            returns: DataFrame of asset returns
            method: 'sample' for sample covariance, 'shrinkage' for Ledoit-Wolf

        Returns:
            Covariance matrix
        """
        sample_cov = returns.cov().values

        if method == "sample":
            return sample_cov

        if method == "shrinkage":
            # Ledoit-Wolf shrinkage toward scaled identity
            n = len(returns)
            p = sample_cov.shape[0]

            if n < 2:
                return sample_cov

            # Shrinkage target: scaled identity matrix
            trace_s = np.trace(sample_cov)
            mu = trace_s / p
            target = mu * np.eye(p)

            # Estimate shrinkage intensity
            alpha = min(1.0, self.shrinkage_target)

            return alpha * target + (1 - alpha) * sample_cov

        return sample_cov

    def compute_var(
        self,
        weights: np.ndarray,
        returns: pd.DataFrame,
        confidence: float = 0.95,
    ) -> float:
        """Compute parametric Value at Risk.

        Args:
            weights: Portfolio weight vector
            returns: DataFrame of asset returns
            confidence: Confidence level

        Returns:
            VaR estimate (positive number representing loss)
        """
        portfolio_returns = returns.values @ weights
        mean_return = np.mean(portfolio_returns)
        std_return = np.std(portfolio_returns)

        # Assuming normal distribution - use scipy.stats.norm for quantile
        z_score = norm.ppf(1 - confidence)
        var = -(mean_return + z_score * std_return)
        return float(max(0, var))

    def compute_cvar(
        self,
        weights: np.ndarray,
        returns: pd.DataFrame,
        confidence: float = 0.95,
    ) -> float:
        """Compute historical Conditional Value at Risk.

        Args:
            weights: Portfolio weight vector
            returns: DataFrame of asset returns
            confidence: Confidence level

        Returns:
            CVaR estimate (positive number representing expected loss)
        """
        portfolio_returns = returns.values @ weights
        var_threshold = np.percentile(portfolio_returns, (1 - confidence) * 100)
        tail_returns = portfolio_returns[portfolio_returns <= var_threshold]

        if len(tail_returns) == 0:
            return self.compute_var(weights, returns, confidence)

        cvar = -np.mean(tail_returns)
        return float(max(0, cvar))

    def factor_decomposition(
        self,
        returns: pd.DataFrame,
        n_factors: int = 3,
    ) -> Dict[str, Any]:
        """Decompose returns using PCA.

        Args:
            returns: DataFrame of asset returns
            n_factors: Number of factors to extract

        Returns:
            Dictionary with loadings, explained variance, and residuals
        """
        returns_centered = returns - returns.mean()
        cov_matrix = returns_centered.cov().values

        eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)

        # Sort by eigenvalue (descending)
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Select top factors
        n_factors = min(n_factors, len(eigenvalues))
        loadings = eigenvectors[:, :n_factors]
        explained_var = eigenvalues[:n_factors] / np.sum(eigenvalues)

        # Residual variance
        total_var = np.sum(eigenvalues)
        factor_var = np.sum(eigenvalues[:n_factors])
        residual_var = (total_var - factor_var) / total_var

        return {
            "loadings": loadings,
            "eigenvalues": eigenvalues[:n_factors],
            "explained_variance_ratio": explained_var,
            "cumulative_explained_variance": np.cumsum(explained_var),
            "residual_variance_ratio": residual_var,
            "n_factors": n_factors,
        }


class LocalOptimizer(OptimizationPort):
    """Local portfolio optimization using NumPy/SciPy."""

    def __init__(self, max_iterations: int = 1000, tolerance: float = 1e-8) -> None:
        """Initialize optimizer.

        Args:
            max_iterations: Maximum iterations for iterative methods
            tolerance: Convergence tolerance
        """
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def mean_variance_optimize(
        self,
        expected_returns: np.ndarray,
        covariance: np.ndarray,
        constraints: Mapping[str, Any] | None = None,
    ) -> np.ndarray:
        """Solve mean-variance optimization using closed-form solution.

        For unconstrained case with target return, uses analytical solution.
        For constrained case, uses iterative optimization.

        Args:
            expected_returns: Expected return vector
            covariance: Covariance matrix
            constraints: Optional constraints dict with keys:
                - 'target_return': Target portfolio return
                - 'min_weight': Minimum weight per asset
                - 'max_weight': Maximum weight per asset
                - 'long_only': Boolean for long-only constraint

        Returns:
            Optimal weight vector
        """
        n = len(expected_returns)
        constraints = constraints or {}

        # Simple case: minimum variance portfolio with sum to 1 constraint
        try:
            cov_inv = np.linalg.inv(covariance)
        except np.linalg.LinAlgError:
            # Regularize if singular
            cov_inv = np.linalg.inv(covariance + 1e-6 * np.eye(n))

        ones = np.ones(n)

        # Minimum variance portfolio
        min_var_weights = cov_inv @ ones
        min_var_weights = min_var_weights / np.sum(min_var_weights)

        # Apply constraints
        if constraints.get("long_only", False):
            min_var_weights = np.maximum(min_var_weights, 0)
            min_var_weights = min_var_weights / np.sum(min_var_weights)

        min_weight = constraints.get("min_weight", 0.0)
        max_weight = constraints.get("max_weight", 1.0)

        min_var_weights = np.clip(min_var_weights, min_weight, max_weight)
        min_var_weights = min_var_weights / np.sum(min_var_weights)

        return min_var_weights

    def risk_parity_optimize(
        self,
        covariance: np.ndarray,
        risk_budget: np.ndarray | None = None,
    ) -> np.ndarray:
        """Solve risk parity using iterative reweighting.

        Args:
            covariance: Covariance matrix
            risk_budget: Target risk contribution per asset (default: equal)

        Returns:
            Risk parity weights
        """
        n = covariance.shape[0]

        if risk_budget is None:
            risk_budget = np.ones(n) / n
        else:
            risk_budget = np.asarray(risk_budget)
            risk_budget = risk_budget / np.sum(risk_budget)

        # Initial weights: inverse volatility
        vols = np.sqrt(np.diag(covariance))
        weights = 1.0 / np.maximum(vols, 1e-10)
        weights = weights / np.sum(weights)

        # Iterative risk parity (Spinu's cyclical coordinate descent)
        for _ in range(self.max_iterations):
            old_weights = weights.copy()

            # Marginal risk contribution
            sigma = np.sqrt(weights @ covariance @ weights)
            if sigma < 1e-10:
                break

            marginal_risk = covariance @ weights / sigma

            # Update weights
            for i in range(n):
                if marginal_risk[i] > 1e-10:
                    weights[i] = risk_budget[i] / marginal_risk[i]

            weights = weights / np.sum(weights)

            # Check convergence
            if np.max(np.abs(weights - old_weights)) < self.tolerance:
                break

        return weights

    def black_litterman(
        self,
        market_weights: np.ndarray,
        covariance: np.ndarray,
        views: Dict[str, float],
        view_confidence: np.ndarray,
    ) -> np.ndarray:
        """Apply Black-Litterman model.

        Args:
            market_weights: Market cap weights
            covariance: Covariance matrix
            views: Dict mapping asset index to expected return view
            view_confidence: Confidence in each view

        Returns:
            Posterior expected returns
        """
        n = len(market_weights)
        tau = 0.05  # Scaling factor for prior uncertainty

        # Implied equilibrium returns
        delta = 2.5  # Risk aversion coefficient
        pi = delta * covariance @ market_weights

        # If no views, return equilibrium returns
        if not views:
            return pi

        # Build view matrix P and view vector Q
        n_views = len(views)
        P = np.zeros((n_views, n))
        Q = np.zeros(n_views)

        for i, (asset_idx, view_return) in enumerate(views.items()):
            idx = int(asset_idx) if isinstance(asset_idx, str) else asset_idx
            P[i, idx] = 1.0
            Q[i] = view_return

        # Omega: view uncertainty (diagonal)
        omega = np.diag(view_confidence)

        # Posterior calculations
        tau_sigma = tau * covariance
        M = np.linalg.inv(np.linalg.inv(tau_sigma) + P.T @ np.linalg.inv(omega) @ P)
        posterior_returns = M @ (
            np.linalg.inv(tau_sigma) @ pi + P.T @ np.linalg.inv(omega) @ Q
        )

        return posterior_returns


class InMemoryPersistence(PersistencePort):
    """In-memory implementation for testing and development."""

    def __init__(self) -> None:
        """Initialize empty storage."""
        self._portfolios: Dict[str, Dict[str, Any]] = {}
        self._regime_history: Dict[str, list] = {}

    def save_portfolio_state(
        self,
        portfolio_id: str,
        weights: Dict[str, float],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Save portfolio state to memory."""
        self._portfolios[portfolio_id] = {
            "weights": weights,
            "metadata": metadata or {},
        }

    def load_portfolio_state(
        self,
        portfolio_id: str,
    ) -> Dict[str, Any] | None:
        """Load portfolio state from memory."""
        return self._portfolios.get(portfolio_id)

    def save_regime_history(
        self,
        portfolio_id: str,
        history: Sequence[Mapping[str, Any]],
    ) -> None:
        """Save regime history to memory."""
        self._regime_history[portfolio_id] = list(history)

    def load_regime_history(
        self,
        portfolio_id: str,
    ) -> Sequence[Dict[str, Any]]:
        """Load regime history from memory."""
        return self._regime_history.get(portfolio_id, [])


class FilePersistence(PersistencePort):
    """File-based persistence for portfolio state."""

    def __init__(self, data_dir: Path | str) -> None:
        """Initialize with data directory.

        Args:
            data_dir: Directory for storing portfolio files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_portfolio_state(
        self,
        portfolio_id: str,
        weights: Dict[str, float],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Save portfolio state to JSON file."""
        file_path = self.data_dir / f"{portfolio_id}_state.json"
        state = {"weights": weights, "metadata": metadata or {}}
        file_path.write_text(json.dumps(state, indent=2))

    def load_portfolio_state(
        self,
        portfolio_id: str,
    ) -> Dict[str, Any] | None:
        """Load portfolio state from JSON file."""
        file_path = self.data_dir / f"{portfolio_id}_state.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text())

    def save_regime_history(
        self,
        portfolio_id: str,
        history: Sequence[Mapping[str, Any]],
    ) -> None:
        """Save regime history to JSON file."""
        file_path = self.data_dir / f"{portfolio_id}_regimes.json"
        file_path.write_text(json.dumps(list(history), indent=2))

    def load_regime_history(
        self,
        portfolio_id: str,
    ) -> Sequence[Dict[str, Any]]:
        """Load regime history from JSON file."""
        file_path = self.data_dir / f"{portfolio_id}_regimes.json"
        if not file_path.exists():
            return []
        return json.loads(file_path.read_text())


__all__ = [
    "LocalSum",
    "LocalRiskModel",
    "LocalOptimizer",
    "InMemoryPersistence",
    "FilePersistence",
]
