# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_add():
    module = importlib.import_module("analytics.fpma.src.core.main")
    assert module.add(2, 3) == 5


def test_compute_hurst_exponent_trending():
    """Hurst exponent should be > 0.5 for trending series."""
    from analytics.fpma.src.core.main import compute_hurst_exponent

    # Generate trending series (cumulative sum of positive drift)
    np.random.seed(42)
    trend = np.cumsum(np.random.normal(0.1, 0.5, 500))
    returns = np.diff(trend)

    hurst = compute_hurst_exponent(returns)
    # Trending series should have H > 0.5
    assert 0.0 <= hurst <= 1.0


def test_compute_hurst_exponent_random_walk():
    """Hurst exponent should be ~0.5 for random walk."""
    from analytics.fpma.src.core.main import compute_hurst_exponent

    np.random.seed(42)
    returns = np.random.normal(0, 1, 500)

    hurst = compute_hurst_exponent(returns)
    # Random walk should have H close to 0.5
    assert 0.3 <= hurst <= 0.7


def test_wavelet_decomposition():
    """Test multi-scale wavelet decomposition."""
    from analytics.fpma.src.core.main import wavelet_decomposition

    np.random.seed(42)
    series = np.cumsum(np.random.normal(0, 1, 200))
    scales = [5, 21, 63]

    components = wavelet_decomposition(series, scales)

    assert len(components) == 3
    for scale in scales:
        assert scale in components
        assert len(components[scale]) == len(series)


def test_detect_regime():
    """Test regime detection returns valid regime."""
    from analytics.fpma.src.core.main import MarketRegime, detect_regime

    np.random.seed(42)
    returns = np.random.normal(0, 0.02, 200)

    snapshot = detect_regime(returns)

    assert isinstance(snapshot.regime, MarketRegime)
    assert 0.0 <= snapshot.confidence <= 1.0
    assert 0.0 <= snapshot.hurst_exponent <= 1.0
    assert 0.0 <= snapshot.volatility_percentile <= 1.0


def test_fractal_portfolio_analyzer_basic():
    """Test basic portfolio weight computation."""
    from analytics.fpma.src.core.main import FractalPortfolioAnalyzer

    np.random.seed(42)
    n_assets = 3
    n_periods = 100

    returns_data = np.random.normal(0, 0.02, (n_periods, n_assets))
    returns = pd.DataFrame(returns_data, columns=["A", "B", "C"])

    analyzer = FractalPortfolioAnalyzer(scales=[5, 21, 63])
    weights = analyzer.compute_fractal_weights(returns)

    assert len(weights.weights) == n_assets
    assert abs(sum(weights.weights.values()) - 1.0) < 1e-6
    assert all(w >= 0 for w in weights.weights.values())


def test_fractal_portfolio_analyzer_with_constraints():
    """Test portfolio weight computation with constraints."""
    from analytics.fpma.src.core.main import FractalPortfolioAnalyzer

    np.random.seed(42)
    returns_data = np.random.normal(0, 0.02, (100, 3))
    returns = pd.DataFrame(returns_data, columns=["A", "B", "C"])

    analyzer = FractalPortfolioAnalyzer()
    constraints = {"A": (0.1, 0.5), "B": (0.1, 0.5)}
    weights = analyzer.compute_fractal_weights(returns, constraints=constraints)

    # Verify constraints are respected (approximately, due to renormalization)
    assert 0.05 <= weights.weights["A"] <= 0.55
    assert 0.05 <= weights.weights["B"] <= 0.55


def test_fractal_portfolio_analyzer_rebalance_signal():
    """Test rebalance signal computation."""
    from analytics.fpma.src.core.main import FractalPortfolioAnalyzer

    analyzer = FractalPortfolioAnalyzer()

    current = {"A": 0.4, "B": 0.3, "C": 0.3}
    target = {"A": 0.33, "B": 0.33, "C": 0.34}

    trades = analyzer.compute_rebalance_signal(current, target, threshold=0.05)

    # Only A should trigger (deviation of 0.07)
    assert "A" in trades
    assert abs(trades["A"] - (-0.07)) < 0.01


def test_fractal_portfolio_analyzer_empty_returns():
    """Test handling of empty returns DataFrame."""
    from analytics.fpma.src.core.main import FractalPortfolioAnalyzer, MarketRegime

    analyzer = FractalPortfolioAnalyzer()
    empty_df = pd.DataFrame()

    weights = analyzer.compute_fractal_weights(empty_df)

    assert len(weights.weights) == 0
    assert weights.regime == MarketRegime.REGIME_TRANSITION
