# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive integration tests validating the full trading workflow.

This module tests the complete end-to-end workflow from data ingestion
through analysis, backtesting, and execution validation. These tests
ensure that all major components work together correctly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.engine import walk_forward
from backtest.event_driven import EventDrivenBacktestEngine
from core.indicators.entropy import delta_entropy, entropy
from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine
from core.indicators.ricci import build_price_graph, mean_ricci
from core.phase.detector import composite_transition, phase_flags


@pytest.fixture
def synthetic_market_data() -> pd.DataFrame:
    """Generate synthetic market data with regime changes for testing."""
    np.random.seed(42)
    n = 1000

    # Create three distinct regimes
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")

    # Regime 1: Random walk (accumulation)
    r1 = np.cumsum(np.random.normal(0, 0.3, n // 3))

    # Regime 2: Strong trend (trending)
    r2 = r1[-1] + 0.1 * np.arange(n // 3) + np.random.normal(0, 0.1, n // 3)

    # Regime 3: Volatile (distribution)
    r3 = r2[-1] + np.cumsum(np.random.normal(0, 0.8, n - 2 * (n // 3)))

    prices = 100 + np.concatenate([r1, r2, r3])
    volume = np.random.lognormal(10, 0.5, n)

    return pd.DataFrame(
        {
            "close": prices,
            "volume": volume,
            "open": prices * 0.999,
            "high": prices * 1.001,
            "low": prices * 0.998,
        },
        index=idx,
    )


class TestIndicatorPipeline:
    """Test the indicator computation pipeline."""

    def test_kuramoto_order_valid_range(self, synthetic_market_data: pd.DataFrame):
        """Kuramoto order parameter should be in [0, 1]."""
        prices = synthetic_market_data["close"].to_numpy()
        phases = compute_phase(prices)
        R = kuramoto_order(phases)

        assert 0 <= R <= 1, f"Kuramoto order {R} outside valid range [0, 1]"

    def test_entropy_positive(self, synthetic_market_data: pd.DataFrame):
        """Entropy should be non-negative."""
        prices = synthetic_market_data["close"].to_numpy()
        H = entropy(prices, bins=30)

        assert H >= 0, f"Entropy {H} should be non-negative"

    def test_delta_entropy_finite(self, synthetic_market_data: pd.DataFrame):
        """Delta entropy should be finite."""
        prices = synthetic_market_data["close"].to_numpy()
        dH = delta_entropy(prices, window=50)

        assert np.isfinite(dH), f"Delta entropy {dH} should be finite"

    def test_hurst_exponent_valid_range(self, synthetic_market_data: pd.DataFrame):
        """Hurst exponent should be in (0, 1) range."""
        prices = synthetic_market_data["close"].to_numpy()
        H = hurst_exponent(prices)

        assert 0 < H < 1, f"Hurst exponent {H} outside valid range (0, 1)"

    def test_ricci_curvature_computable(self, synthetic_market_data: pd.DataFrame):
        """Ricci curvature should be computable from price data."""
        prices = synthetic_market_data["close"].to_numpy()
        graph = build_price_graph(prices[-200:], delta=0.005)
        kappa = mean_ricci(graph)

        assert np.isfinite(kappa), f"Ricci curvature {kappa} should be finite"


class TestCompositeEngine:
    """Test the TradePulse composite analysis engine."""

    def test_analyze_market_returns_valid_snapshot(
        self, synthetic_market_data: pd.DataFrame
    ):
        """Composite engine should return valid market snapshot."""
        engine = TradePulseCompositeEngine()
        snapshot = engine.analyze_market(synthetic_market_data)

        assert hasattr(snapshot, "phase")
        assert hasattr(snapshot, "confidence")
        assert hasattr(snapshot, "entry_signal")

        assert 0 <= snapshot.confidence <= 1
        assert snapshot.phase.value in [
            "accumulation",
            "distribution",
            "trending",
            "transition",
        ]

    def test_analyze_market_handles_minimal_data(self):
        """Engine should handle edge case with minimal data."""
        minimal_data = pd.DataFrame(
            {"close": [100, 101, 102, 103, 104] * 60, "volume": [1000] * 300},
            index=pd.date_range("2024-01-01", periods=300, freq="1min"),
        )

        engine = TradePulseCompositeEngine()
        snapshot = engine.analyze_market(minimal_data)

        assert snapshot is not None
        assert hasattr(snapshot, "phase")


class TestBacktestingWorkflow:
    """Test backtesting workflows."""

    def test_walk_forward_basic(self, synthetic_market_data: pd.DataFrame):
        """Walk-forward backtest should complete without errors."""
        prices = synthetic_market_data["close"].to_numpy()

        def simple_signal(p: np.ndarray) -> np.ndarray:
            """Simple moving average crossover signal."""
            signal = np.zeros_like(p)
            short_ma = pd.Series(p).rolling(10).mean().to_numpy()
            long_ma = pd.Series(p).rolling(50).mean().to_numpy()
            signal[50:] = np.where(short_ma[50:] > long_ma[50:], 1, -1)
            return signal

        result = walk_forward(prices, simple_signal, fee=0.0005)

        assert hasattr(result, "pnl")
        assert hasattr(result, "max_dd")
        assert hasattr(result, "trades")
        assert result.max_dd <= 0  # Max drawdown should be <= 0

    def test_event_driven_backtest_engine(self, synthetic_market_data: pd.DataFrame):
        """Event-driven backtest should execute successfully."""
        prices = synthetic_market_data["close"].to_numpy()

        def kuramoto_signal(series: np.ndarray) -> np.ndarray:
            """Signal based on Kuramoto synchronization."""
            phases = compute_phase(series)
            R_values = np.array(
                [
                    kuramoto_order(phases[max(0, i - 50) : i + 1]) if i >= 50 else 0.5
                    for i in range(len(phases))
                ]
            )
            signal = np.where(R_values > 0.7, 1.0, np.where(R_values < 0.3, -1.0, 0.0))
            signal[:50] = 0  # Warmup period
            return signal

        engine = EventDrivenBacktestEngine()
        result = engine.run(
            prices,
            kuramoto_signal,
            initial_capital=100_000,
            strategy_name="kuramoto_test",
        )

        assert hasattr(result, "pnl")
        assert hasattr(result, "trades")


class TestPhaseDetection:
    """Test phase detection and transition scoring."""

    def test_phase_flags_valid_output(self, synthetic_market_data: pd.DataFrame):
        """Phase flags should return valid classifications."""
        prices = synthetic_market_data["close"].to_numpy()
        window = 200

        phases = compute_phase(prices[-window:])
        R = kuramoto_order(phases)
        H = entropy(prices[-window:], bins=30)
        dH = delta_entropy(prices, window=window)
        graph = build_price_graph(prices[-window:], delta=0.005)
        kappa = mean_ricci(graph)

        flag = phase_flags(R=R, dH=dH, kappa_mean=kappa, H=H)

        valid_flags = {"proto", "precognitive", "emergent", "post-emergent", "neutral"}
        assert flag in valid_flags, f"Invalid phase flag: {flag}"

    def test_composite_transition_bounded(self, synthetic_market_data: pd.DataFrame):
        """Composite transition score should be bounded [-1, 1]."""
        prices = synthetic_market_data["close"].to_numpy()
        window = 200

        phases = compute_phase(prices[-window:])
        R = kuramoto_order(phases)
        H = entropy(prices[-window:], bins=30)
        dH = delta_entropy(prices, window=window)
        graph = build_price_graph(prices[-window:], delta=0.005)
        kappa = mean_ricci(graph)

        score = composite_transition(R, dH, kappa, H)

        assert -1 <= score <= 1, f"Transition score {score} outside [-1, 1]"


class TestDataPersistence:
    """Test data saving and loading workflows."""

    def test_csv_roundtrip(self, synthetic_market_data: pd.DataFrame):
        """Data should survive CSV save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_data.csv"

            # Save
            synthetic_market_data.to_csv(path)

            # Load and verify
            loaded = pd.read_csv(path, index_col=0, parse_dates=True)

            np.testing.assert_array_almost_equal(
                synthetic_market_data["close"].values,
                loaded["close"].values,
                decimal=6,
            )


class TestEndToEndWorkflow:
    """Test complete end-to-end trading workflow."""

    def test_full_analysis_to_backtest_pipeline(
        self, synthetic_market_data: pd.DataFrame
    ):
        """Full workflow from analysis through backtesting."""
        # Step 1: Analyze market regime
        engine = TradePulseCompositeEngine()
        snapshot = engine.analyze_market(synthetic_market_data)

        # Step 2: Generate trading signal based on analysis
        prices = synthetic_market_data["close"].to_numpy()

        def adaptive_signal(p: np.ndarray) -> np.ndarray:
            """Generate signal based on market regime."""
            signal = np.zeros_like(p)

            # Use phase and confidence for signal generation
            if snapshot.confidence > 0.6:
                if snapshot.phase.value == "trending":
                    # Momentum strategy in trending markets
                    returns = np.diff(p, prepend=p[0])
                    signal = np.where(returns > 0, 1.0, -1.0)
                elif snapshot.phase.value in ["accumulation", "distribution"]:
                    # Mean reversion in ranging markets
                    ma = pd.Series(p).rolling(20).mean().to_numpy()
                    signal = np.where(p < ma, 1.0, -1.0)

            # No signal during warmup
            signal[:100] = 0
            return signal

        # Step 3: Backtest the strategy
        result = walk_forward(prices, adaptive_signal, fee=0.0005)

        # Step 4: Validate results
        assert result is not None
        assert isinstance(result.pnl, (int, float))
        assert isinstance(result.trades, int)
        assert result.max_dd <= 0

        # Log summary for debugging
        print("\n=== End-to-End Workflow Summary ===")
        print(f"Market Phase: {snapshot.phase.value}")
        print(f"Confidence: {snapshot.confidence:.3f}")
        print(f"Entry Signal: {snapshot.entry_signal:.3f}")
        print(f"Backtest PnL: {result.pnl:.2f}")
        print(f"Trades: {result.trades}")
        print(f"Max Drawdown: {result.max_dd:.2f}")
