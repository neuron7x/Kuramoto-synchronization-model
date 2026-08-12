# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Local adapter implementations for regime detection ports.

This module provides concrete implementations of regime detection port interfaces
for local (in-process) execution. The hexagonal architecture enables clean
separation between regime classification logic and infrastructure details.

Available Implementations:
    LocalSum: Basic arithmetic adapter (backward compatibility)
    LocalRegimeClassifier: In-memory regime detection using K-means
    LocalFeatureExtractor: Statistical feature extraction
    LocalTransitionModel: Markov chain transition modeling
    InMemoryRegimePersistence: In-memory storage for testing
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import pandas as pd

from analytics.regime.src.ports.ports import (
    FeatureExtractionPort,
    RegimeClassifierPort,
    RegimePersistencePort,
    SumPort,
    TransitionModelPort,
)


class LocalSum(SumPort):
    """Local implementation of the SumPort interface."""

    def sum(self, a: int, b: int) -> int:
        """Compute sum of two integers."""
        return a + b


class LocalRegimeClassifier(RegimeClassifierPort):
    """K-means based regime classifier for market states.

    Classifies market states based on volatility, returns, and other features.
    """

    def __init__(self, random_state: int = 42) -> None:
        """Initialize classifier.

        Args:
            random_state: Random seed for reproducibility
        """
        self.random_state = random_state
        self.n_regimes = 3
        self._centroids: np.ndarray | None = None
        self._regime_stats: Dict[int, Dict[str, float]] = {}
        self._fitted = False

    def fit(
        self,
        returns: pd.DataFrame,
        n_regimes: int = 3,
    ) -> None:
        """Train the regime classifier using simplified K-means.

        Args:
            returns: DataFrame of asset returns
            n_regimes: Number of regimes to identify
        """
        self.n_regimes = n_regimes

        # Extract features: mean return and volatility per observation
        features = self._extract_features(returns)

        if len(features) < n_regimes:
            # Not enough data points
            self._centroids = np.zeros((n_regimes, features.shape[1]))
            self._fitted = True
            return

        # Simple K-means clustering
        np.random.seed(self.random_state)

        # Initialize centroids randomly
        indices = np.random.choice(len(features), n_regimes, replace=False)
        self._centroids = features[indices].copy()

        # Run K-means iterations
        for _ in range(100):
            # Assign points to nearest centroid
            distances = np.zeros((len(features), n_regimes))
            for k in range(n_regimes):
                distances[:, k] = np.linalg.norm(features - self._centroids[k], axis=1)
            labels = np.argmin(distances, axis=1)

            # Update centroids
            new_centroids = np.zeros_like(self._centroids)
            for k in range(n_regimes):
                mask = labels == k
                if np.sum(mask) > 0:
                    new_centroids[k] = features[mask].mean(axis=0)
                else:
                    new_centroids[k] = self._centroids[k]

            # Check convergence
            if np.allclose(self._centroids, new_centroids):
                break
            self._centroids = new_centroids

        # Compute regime statistics
        final_labels = self._predict_labels(features)
        self._compute_regime_stats(returns, final_labels)
        self._fitted = True

    def predict(
        self,
        returns: pd.DataFrame,
    ) -> Sequence[int]:
        """Predict regime for each observation.

        Args:
            returns: DataFrame of asset returns

        Returns:
            List of regime labels
        """
        if not self._fitted:
            return [0] * len(returns)

        features = self._extract_features(returns)
        return list(self._predict_labels(features))

    def predict_proba(
        self,
        returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """Predict regime probabilities using softmax of distances.

        Args:
            returns: DataFrame of asset returns

        Returns:
            DataFrame with regime probabilities
        """
        if not self._fitted or self._centroids is None:
            n = len(returns)
            proba = np.ones((n, self.n_regimes)) / self.n_regimes
            return pd.DataFrame(
                proba,
                columns=[f"regime_{i}" for i in range(self.n_regimes)],
                index=returns.index,
            )

        features = self._extract_features(returns)
        distances = np.zeros((len(features), self.n_regimes))
        for k in range(self.n_regimes):
            distances[:, k] = np.linalg.norm(features - self._centroids[k], axis=1)

        # Convert distances to probabilities using softmax
        # Negate distances so smaller distance = higher probability
        exp_neg_dist = np.exp(-distances)
        probabilities = exp_neg_dist / exp_neg_dist.sum(axis=1, keepdims=True)

        return pd.DataFrame(
            probabilities,
            columns=[f"regime_{i}" for i in range(self.n_regimes)],
            index=returns.index,
        )

    def get_regime_statistics(self) -> Dict[int, Dict[str, float]]:
        """Get descriptive statistics for each regime."""
        return self._regime_stats

    def _extract_features(self, returns: pd.DataFrame) -> np.ndarray:
        """Extract features for clustering."""
        # Rolling mean and volatility
        window = min(5, len(returns))
        if window < 2:
            window = len(returns)

        mean_returns = returns.rolling(window).mean().mean(axis=1).fillna(0).values
        volatility = returns.rolling(window).std().mean(axis=1).fillna(0).values

        features = np.column_stack([mean_returns, volatility])
        return features

    def _predict_labels(self, features: np.ndarray) -> np.ndarray:
        """Predict cluster labels for features."""
        if self._centroids is None:
            return np.zeros(len(features), dtype=int)

        distances = np.zeros((len(features), self.n_regimes))
        for k in range(self.n_regimes):
            distances[:, k] = np.linalg.norm(features - self._centroids[k], axis=1)
        return np.argmin(distances, axis=1)

    def _compute_regime_stats(self, returns: pd.DataFrame, labels: np.ndarray) -> None:
        """Compute statistics for each regime."""
        self._regime_stats = {}
        for k in range(self.n_regimes):
            mask = labels == k
            if np.sum(mask) == 0:
                self._regime_stats[k] = {"mean": 0.0, "volatility": 0.0, "count": 0}
                continue

            regime_returns = returns.iloc[mask]
            self._regime_stats[k] = {
                "mean": float(regime_returns.mean().mean()),
                "volatility": float(regime_returns.std().mean()),
                "count": int(np.sum(mask)),
                "duration_mean": float(self._compute_mean_duration(labels, k)),
            }

    @staticmethod
    def _compute_mean_duration(labels: np.ndarray, target_regime: int) -> float:
        """Compute mean duration of consecutive periods in a regime."""
        if len(labels) == 0:
            return 0.0

        durations = []
        current_duration = 0

        for label in labels:
            if label == target_regime:
                current_duration += 1
            elif current_duration > 0:
                durations.append(current_duration)
                current_duration = 0

        if current_duration > 0:
            durations.append(current_duration)

        return float(np.mean(durations)) if durations else 0.0


class LocalFeatureExtractor(FeatureExtractionPort):
    """Local implementation of feature extraction for regime detection."""

    def __init__(
        self,
        windows: Sequence[int] = (5, 10, 21),
        include_momentum: bool = True,
        include_volatility: bool = True,
    ) -> None:
        """Initialize feature extractor.

        Args:
            windows: Rolling window sizes for feature computation
            include_momentum: Whether to compute momentum features
            include_volatility: Whether to compute volatility features
        """
        self.windows = list(windows)
        self.include_momentum = include_momentum
        self.include_volatility = include_volatility
        self._feature_names: list[str] = []
        self._feature_importance: Dict[str, float] = {}

    def extract(
        self,
        prices: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """Extract features from price and return data."""
        features: Dict[str, pd.Series] = {}
        self._feature_names = []

        # Compute features for each window size
        for window in self.windows:
            if len(returns) < window:
                continue

            if self.include_momentum:
                # Momentum (cumulative return over window)
                momentum = returns.rolling(window).sum().mean(axis=1)
                name = f"momentum_{window}"
                features[name] = momentum
                self._feature_names.append(name)

            if self.include_volatility:
                # Rolling volatility
                vol = returns.rolling(window).std().mean(axis=1)
                name = f"volatility_{window}"
                features[name] = vol
                self._feature_names.append(name)

                # Volatility ratio (current vs longer-term)
                if window != max(self.windows):
                    long_vol = returns.rolling(max(self.windows)).std().mean(axis=1)
                    ratio = vol / long_vol.replace(0, np.nan)
                    name = f"vol_ratio_{window}"
                    features[name] = ratio
                    self._feature_names.append(name)

        # Cross-sectional features
        if returns.shape[1] >= 2:
            # Average correlation
            corr_series = returns.rolling(min(21, len(returns))).corr()
            if isinstance(corr_series, pd.DataFrame):
                mean_corr = corr_series.groupby(level=0).apply(
                    lambda x: (x.values[np.triu_indices(len(x), k=1)].mean() if len(x) > 1 else 0.0)
                )
                features["cross_correlation"] = mean_corr
                self._feature_names.append("cross_correlation")

        result = pd.DataFrame(features, index=returns.index).fillna(0)

        # Initialize uniform importance
        n_features = len(self._feature_names)
        if n_features > 0:
            self._feature_importance = {name: 1.0 / n_features for name in self._feature_names}

        return result

    def get_feature_names(self) -> Sequence[str]:
        """Return names of features being extracted."""
        return self._feature_names

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        return self._feature_importance


class LocalTransitionModel(TransitionModelPort):
    """Markov chain based regime transition model."""

    def __init__(self, smoothing: float = 0.01) -> None:
        """Initialize transition model.

        Args:
            smoothing: Laplace smoothing parameter for probability estimation
        """
        self.smoothing = smoothing
        self._n_regimes = 0
        self._transition_counts: np.ndarray | None = None
        self._transition_matrix: np.ndarray | None = None
        self._regime_durations: Dict[int, list[int]] = defaultdict(list)

    def fit(
        self,
        regime_sequence: Sequence[int],
        features: pd.DataFrame | None = None,
    ) -> None:
        """Fit the transition model on observed regime sequence."""
        if len(regime_sequence) < 2:
            return

        # Determine number of regimes
        self._n_regimes = max(regime_sequence) + 1

        # Count transitions
        self._transition_counts = np.zeros((self._n_regimes, self._n_regimes))
        for i in range(len(regime_sequence) - 1):
            current = regime_sequence[i]
            next_regime = regime_sequence[i + 1]
            self._transition_counts[current, next_regime] += 1

        # Compute transition probabilities with smoothing
        row_sums = self._transition_counts.sum(axis=1, keepdims=True)
        self._transition_matrix = (self._transition_counts + self.smoothing) / (
            row_sums + self.smoothing * self._n_regimes
        )

        # Compute regime durations
        self._regime_durations = defaultdict(list)
        current_regime = regime_sequence[0]
        current_duration = 1

        for i in range(1, len(regime_sequence)):
            if regime_sequence[i] == current_regime:
                current_duration += 1
            else:
                self._regime_durations[current_regime].append(current_duration)
                current_regime = regime_sequence[i]
                current_duration = 1

        self._regime_durations[current_regime].append(current_duration)

    def get_transition_matrix(self) -> pd.DataFrame:
        """Get estimated transition probability matrix."""
        if self._transition_matrix is None:
            return pd.DataFrame()

        return pd.DataFrame(
            self._transition_matrix,
            index=[f"from_regime_{i}" for i in range(self._n_regimes)],
            columns=[f"to_regime_{i}" for i in range(self._n_regimes)],
        )

    def predict_next_regime(
        self,
        current_regime: int,
        features: Mapping[str, float] | None = None,
    ) -> Dict[int, float]:
        """Predict probability distribution over next regime."""
        if self._transition_matrix is None or current_regime >= self._n_regimes:
            # Uniform distribution
            return {i: 1.0 / max(self._n_regimes, 1) for i in range(self._n_regimes)}

        probs = self._transition_matrix[current_regime]
        return {i: float(probs[i]) for i in range(self._n_regimes)}

    def expected_duration(self, regime: int) -> float:
        """Estimate expected duration of a regime in periods."""
        durations = self._regime_durations.get(regime, [])
        if not durations:
            # Use geometric distribution based on self-transition probability
            if self._transition_matrix is not None and regime < self._n_regimes:
                p_stay = self._transition_matrix[regime, regime]
                if p_stay < 1.0:
                    return 1.0 / (1.0 - p_stay)
            return 1.0

        return float(np.mean(durations))


class InMemoryRegimePersistence(RegimePersistencePort):
    """In-memory implementation for testing and development."""

    def __init__(self) -> None:
        """Initialize empty storage."""
        self._sequences: Dict[str, Dict[str, Any]] = {}
        self._models: Dict[str, Dict[str, Any]] = {}

    def save_regime_sequence(
        self,
        identifier: str,
        timestamps: Sequence[str],
        regimes: Sequence[int],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist a regime detection sequence."""
        self._sequences[identifier] = {
            "timestamps": list(timestamps),
            "regimes": list(regimes),
            "metadata": dict(metadata) if metadata else {},
        }

    def load_regime_sequence(
        self,
        identifier: str,
    ) -> Dict[str, Any] | None:
        """Load a previously saved regime sequence."""
        return self._sequences.get(identifier)

    def save_model_state(
        self,
        model_id: str,
        state: Dict[str, Any],
    ) -> None:
        """Persist trained model parameters."""
        self._models[model_id] = dict(state)

    def load_model_state(
        self,
        model_id: str,
    ) -> Dict[str, Any] | None:
        """Load previously saved model state."""
        return self._models.get(model_id)


class FileRegimePersistence(RegimePersistencePort):
    """File-based persistence for regime data."""

    def __init__(self, data_dir: Path | str) -> None:
        """Initialize with data directory.

        Args:
            data_dir: Directory for storing regime files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_regime_sequence(
        self,
        identifier: str,
        timestamps: Sequence[str],
        regimes: Sequence[int],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist a regime detection sequence to JSON file."""
        file_path = self.data_dir / f"{identifier}_sequence.json"
        data = {
            "timestamps": list(timestamps),
            "regimes": list(regimes),
            "metadata": dict(metadata) if metadata else {},
        }
        file_path.write_text(json.dumps(data, indent=2))

    def load_regime_sequence(
        self,
        identifier: str,
    ) -> Dict[str, Any] | None:
        """Load a regime sequence from JSON file."""
        file_path = self.data_dir / f"{identifier}_sequence.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text())

    def save_model_state(
        self,
        model_id: str,
        state: Dict[str, Any],
    ) -> None:
        """Persist model state to JSON file."""
        file_path = self.data_dir / f"{model_id}_model.json"
        # Convert numpy arrays to lists for JSON serialization
        serializable_state = self._make_serializable(state)
        file_path.write_text(json.dumps(serializable_state, indent=2))

    def load_model_state(
        self,
        model_id: str,
    ) -> Dict[str, Any] | None:
        """Load model state from JSON file."""
        file_path = self.data_dir / f"{model_id}_model.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text())

    @staticmethod
    def _make_serializable(obj: Any) -> Any:
        """Convert numpy types to Python native types."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: FileRegimePersistence._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [FileRegimePersistence._make_serializable(v) for v in obj]
        return obj


__all__ = [
    "LocalSum",
    "LocalRegimeClassifier",
    "LocalFeatureExtractor",
    "LocalTransitionModel",
    "InMemoryRegimePersistence",
    "FileRegimePersistence",
]
