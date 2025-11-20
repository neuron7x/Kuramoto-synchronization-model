"""Tests for Ricci curvature and topological features."""

# Import directly from module files to avoid package __init__
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Import RicciCurvatureGraph
spec = importlib.util.spec_from_file_location(
    "ricci",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/features/ricci.py",
)
ricci_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ricci_module)
RicciCurvatureGraph = ricci_module.RicciCurvatureGraph

# Import TopoSentinel
spec = importlib.util.spec_from_file_location(
    "topo",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/features/topo.py",
)
topo_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topo_module)
TopoSentinel = topo_module.TopoSentinel

# Import CausalGuard
spec = importlib.util.spec_from_file_location(
    "causal",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/features/causal.py",
)
causal_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(causal_module)
CausalGuard = causal_module.CausalGuard


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
            {
                "asset1": np.random.randn(10) * 0.01,
                "asset2": np.random.randn(10) * 0.01,
            },
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
            {f"asset{i}": np.random.randn(n_steps) * 0.02 for i in range(5)},
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

    def test_handles_constant_and_nan_columns(self):
        """Constant or NaN-only columns should return neutral score after filtering."""
        np.random.seed(0)
        dates = pd.date_range("2024-01-01", periods=120, freq="1h")
        returns = pd.DataFrame(
            {
                "asset1": np.random.randn(120) * 0.01,
                "asset2": np.zeros(120),
                "asset3": np.nan,
            },
            index=dates,
        )

        detector = TopoSentinel(window=60)
        result = detector.fit_transform(returns)

        assert result["topo_score"] == 0.0

    def test_returns_zero_when_no_numeric_data(self):
        """Non-numeric frames should short-circuit to zero score."""
        dates = pd.date_range("2024-01-01", periods=60, freq="1h")
        returns = pd.DataFrame({"category": ["A"] * 60}, index=dates)

        detector = TopoSentinel(window=20)
        result = detector.fit_transform(returns)

        assert result["topo_score"] == 0.0

    def test_ignores_infinite_values(self):
        """Infinite values should be treated as missing data without breaking output."""
        np.random.seed(1)
        dates = pd.date_range("2024-01-01", periods=80, freq="1h")
        returns = pd.DataFrame(
            {
                "asset1": np.random.randn(80) * 0.02,
                "asset2": np.random.randn(80) * 0.02,
            },
            index=dates,
        )
        returns.loc[returns.index[10:15], "asset1"] = np.inf
        returns.loc[returns.index[20:25], "asset2"] = -np.inf

        detector = TopoSentinel(window=40)
        result = detector.fit_transform(returns)

        assert 0.0 <= result["topo_score"] <= 1.0

    def test_requires_two_assets_with_variance(self):
        """Less than two informative assets should yield zero topo score."""
        dates = pd.date_range("2024-01-01", periods=80, freq="1h")
        returns = pd.DataFrame(
            {
                "asset1": np.random.randn(80) * 0.02,
                "asset2": np.nan,
                "asset3": 0.0,
            },
            index=dates,
        )

        detector = TopoSentinel(window=40)
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
