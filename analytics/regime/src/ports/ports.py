# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Port definitions (interfaces) for regime detection hexagonal architecture.

This module defines abstract interfaces that establish contracts between regime
detection core logic and external adapters. Using Protocol typing for structural
subtyping enables flexible adapter implementations without coupling.

Available Ports:
    SumPort: Basic arithmetic interface (backward compatibility)
    RegimeClassifierPort: Market regime classification interface
    FeatureExtractionPort: Extract regime-relevant features
    TransitionModelPort: Model regime transition dynamics
    RegimePersistencePort: Store and retrieve regime history

The regime detection framework supports multiple classification schemes
including statistical, HMM-based, and neural approaches through these
unified interfaces.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Protocol, Sequence

import pandas as pd


class SumPort(Protocol):
    """Basic arithmetic interface for backward compatibility."""

    def sum(self, a: int, b: int) -> int:
        """Compute sum of two integers."""
        ...


class RegimeClassifierPort(Protocol):
    """Interface for market regime classification.

    Implementations may use different algorithms (HMM, clustering,
    neural networks) to classify market states.
    """

    def fit(
        self,
        returns: pd.DataFrame,
        n_regimes: int = 3,
    ) -> None:
        """Train the regime classifier on historical data.

        Args:
            returns: DataFrame of asset returns
            n_regimes: Number of regimes to identify
        """
        ...

    def predict(
        self,
        returns: pd.DataFrame,
    ) -> Sequence[int]:
        """Predict regime for each observation.

        Args:
            returns: DataFrame of asset returns

        Returns:
            Sequence of regime labels (0 to n_regimes-1)
        """
        ...

    def predict_proba(
        self,
        returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """Predict regime probabilities for each observation.

        Args:
            returns: DataFrame of asset returns

        Returns:
            DataFrame with regime probabilities per observation
        """
        ...

    def get_regime_statistics(self) -> Dict[int, Dict[str, float]]:
        """Get descriptive statistics for each regime.

        Returns:
            Dict mapping regime ID to statistics (mean, vol, etc.)
        """
        ...


class FeatureExtractionPort(Protocol):
    """Interface for extracting regime-relevant features.

    Implementations compute features that help distinguish regimes.
    """

    def extract(
        self,
        prices: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """Extract features from price and return data.

        Args:
            prices: DataFrame of asset prices
            returns: DataFrame of asset returns

        Returns:
            DataFrame of extracted features
        """
        ...

    def get_feature_names(self) -> Sequence[str]:
        """Return names of features being extracted.

        Returns:
            List of feature names
        """
        ...

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores if available.

        Returns:
            Dict mapping feature name to importance score
        """
        ...


class TransitionModelPort(Protocol):
    """Interface for regime transition modeling.

    Implementations model the dynamics of regime changes.
    """

    def fit(
        self,
        regime_sequence: Sequence[int],
        features: pd.DataFrame | None = None,
    ) -> None:
        """Fit the transition model on observed regime sequence.

        Args:
            regime_sequence: Observed sequence of regime labels
            features: Optional features that may drive transitions
        """
        ...

    def get_transition_matrix(self) -> pd.DataFrame:
        """Get estimated transition probability matrix.

        Returns:
            DataFrame with transition probabilities
        """
        ...

    def predict_next_regime(
        self,
        current_regime: int,
        features: Mapping[str, float] | None = None,
    ) -> Dict[int, float]:
        """Predict probability distribution over next regime.

        Args:
            current_regime: Current regime label
            features: Optional current feature values

        Returns:
            Dict mapping regime ID to probability
        """
        ...

    def expected_duration(self, regime: int) -> float:
        """Estimate expected duration of a regime in periods.

        Args:
            regime: Regime label

        Returns:
            Expected duration in observation periods
        """
        ...


class RegimePersistencePort(Protocol):
    """Interface for persisting regime detection results.

    Implementations handle storage and retrieval of regime history.
    """

    def save_regime_sequence(
        self,
        identifier: str,
        timestamps: Sequence[str],
        regimes: Sequence[int],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist a regime detection sequence.

        Args:
            identifier: Unique identifier for this sequence
            timestamps: ISO timestamps for each observation
            regimes: Detected regime labels
            metadata: Optional metadata about detection
        """
        ...

    def load_regime_sequence(
        self,
        identifier: str,
    ) -> Dict[str, Any] | None:
        """Load a previously saved regime sequence.

        Args:
            identifier: Sequence identifier

        Returns:
            Dict with timestamps, regimes, metadata or None if not found
        """
        ...

    def save_model_state(
        self,
        model_id: str,
        state: Dict[str, Any],
    ) -> None:
        """Persist trained model parameters.

        Args:
            model_id: Unique model identifier
            state: Model state dictionary
        """
        ...

    def load_model_state(
        self,
        model_id: str,
    ) -> Dict[str, Any] | None:
        """Load previously saved model state.

        Args:
            model_id: Model identifier

        Returns:
            Model state dict or None if not found
        """
        ...


__all__ = [
    "SumPort",
    "RegimeClassifierPort",
    "FeatureExtractionPort",
    "TransitionModelPort",
    "RegimePersistencePort",
]
