"""Tests for Ricci curvature and topological features."""

import numpy as np
import pandas as pd
import pytest

from src.tradepulse.features.ricci import RicciCurvatureGraph
from src.tradepulse.features.topo import TopoSentinel
from src.tradepulse.features.causal import CausalGuard


class TestRicciCurvature:
    """Test Ricci curvature computation."""

    def test_clustered_returns(self):
        """Test with clustered correlated returns."""
        np.random.seed(42)
        n_steps = 50
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        # Create two clusters of correlated assets
        base1 = np.random.randn(n_steps) * 0.02
        base2 = np.random.randn(n_steps) * 0.02

        returns = pd.DataFrame(
            {
                "asset1": base1 + np.random.randn(n_steps) * 0.005,
                "asset2": base1 + np.random.randn(n_steps) * 0.005,
                "asset3": base2 + np.random.randn(n_steps) * 0.005,
            },
            index=dates,
        )

        detector = RicciCurvatureGraph(window=30, correlation_threshold=0.3)
        result = detector.fit_transform(returns)

        assert "kappa_min" in result
        assert "edge_kappa" in result
        assert isinstance(result["kappa_min"], float)
        assert isinstance(result["edge_kappa"], dict)

    def test_insufficient_data(self):
        """Test with insufficient data."""
        dates = pd.date_range("2024-01-01", periods=10, freq="1h")
        returns = pd.DataFrame(
            {"asset1": np.random.randn(10) * 0.01, "asset2": np.random.randn(10) * 0.01},
            index=dates,
        )

        detector = RicciCurvatureGraph(window=30)
        with pytest.raises(ValueError, match="Insufficient data"):
            detector.fit_transform(returns)


class TestTopoSentinel:
    """Test topological sentinel."""

    def test_basic_computation(self):
        """Test basic topological score computation."""
        np.random.seed(42)
        n_steps = 100
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        returns = pd.DataFrame(
            {
                f"asset{i}": np.random.randn(n_steps) * 0.02 for i in range(5)
            },
            index=dates,
        )

        detector = TopoSentinel(window=50)
        result = detector.fit_transform(returns)

        assert "topo_score" in result
        assert isinstance(result["topo_score"], float)
        assert 0.0 <= result["topo_score"] <= 1.0

    def test_insufficient_data_returns_zero(self):
        """Test that insufficient data returns topo_score=0.0."""
        dates = pd.date_range("2024-01-01", periods=10, freq="1h")
        returns = pd.DataFrame(
            {"asset1": np.random.randn(10) * 0.01},
            index=dates,
        )

        detector = TopoSentinel(window=50)
        result = detector.fit_transform(returns)

        assert result["topo_score"] == 0.0


class TestCausalGuard:
    """Test causal guard."""

    def test_causal_relationship(self):
        """Test detection of causal relationship."""
        np.random.seed(42)
        n_steps = 100
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        # Create causal relationship: Y depends on lagged X
        X = np.cumsum(np.random.randn(n_steps))
        Y = np.zeros(n_steps)
        Y[0] = np.random.randn()
        for t in range(1, n_steps):
            Y[t] = 0.7 * Y[t - 1] + 0.3 * X[t - 1] + np.random.randn() * 0.1

        df = pd.DataFrame({"target": Y, "driver": X}, index=dates)

        detector = CausalGuard(max_lag=5, n_bins=5, te_threshold=0.001)
        result = detector.fit_transform(df, target="target")

        assert "TE_pass" in result
        assert isinstance(result["TE_pass"], bool)

    def test_no_causality(self):
        """Test with independent variables."""
        np.random.seed(42)
        n_steps = 100
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        df = pd.DataFrame(
            {
                "target": np.random.randn(n_steps),
                "driver": np.random.randn(n_steps),
            },
            index=dates,
        )

        detector = CausalGuard(max_lag=5, te_threshold=0.05)
        result = detector.fit_transform(df, target="target")

        # With independent noise, should likely fail
        assert "TE_pass" in result

    def test_missing_target(self):
        """Test with missing target column."""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})
        detector = CausalGuard()

        with pytest.raises(ValueError, match="Target.*not found"):
            detector.fit_transform(df, target="missing")

    def test_insufficient_data(self):
        """Test with insufficient data."""
        dates = pd.date_range("2024-01-01", periods=5, freq="1h")
        df = pd.DataFrame(
            {"target": [1, 2, 3, 4, 5], "driver": [5, 4, 3, 2, 1]}, index=dates
        )

        detector = CausalGuard(max_lag=5)
        result = detector.fit_transform(df, target="target")

        # Should return TE_pass=False due to insufficient data
        assert result["TE_pass"] is False
