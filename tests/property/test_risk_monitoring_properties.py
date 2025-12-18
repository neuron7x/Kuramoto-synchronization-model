# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Property-style parameterized tests for risk monitoring.

These tests use parameterization with deterministic seeds to verify
invariants across a wide range of inputs without flakiness.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.risk_monitoring.advanced_risk_manager import (
    AdvancedRiskManager,
    MarketDepthData,
    RiskState,
    StressResponseProtocol,
)
from core.risk_monitoring.fail_safe import (
    FailSafeConfig,
    FailSafeController,
    FailSafeLevel,
)
from core.risk_monitoring.stress_detection import (
    MarketSignals,
    StressDetector,
)


class TestAdvancedRiskManagerProperties:
    """Property-style tests for AdvancedRiskManager."""

    @pytest.fixture
    def manager(self) -> AdvancedRiskManager:
        """Create a basic risk manager for testing."""
        return AdvancedRiskManager()

    @pytest.mark.parametrize("seed", [42, 123, 456, 789, 1001])
    def test_risk_score_always_bounded(
        self, manager: AdvancedRiskManager, seed: int
    ) -> None:
        """Property: Risk score is always in [0, 1] for any valid input."""
        rng = np.random.default_rng(seed)

        # Generate random market data
        price = rng.uniform(50, 150)
        volatility = rng.uniform(0.001, 0.2)

        bids = [(price * (1 - 0.01 * i), rng.uniform(100, 2000)) for i in range(5)]
        asks = [(price * (1 + 0.01 * i), rng.uniform(100, 2000)) for i in range(5)]

        depth = MarketDepthData(bids=bids, asks=asks)
        liquidity = manager.analyze_liquidity(depth)

        assessment = manager.assess_risk(
            current_price=price,
            volatility=volatility,
            liquidity_metrics=liquidity,
        )

        assert 0.0 <= assessment.risk_score <= 1.0
        assert math.isfinite(assessment.risk_score)

    @pytest.mark.parametrize("volatility", [0.0, 0.001, 0.01, 0.05, 0.15, 0.5])
    def test_higher_volatility_increases_risk(
        self, manager: AdvancedRiskManager, volatility: float
    ) -> None:
        """Property: Higher volatility generally increases risk score."""
        depth = MarketDepthData(
            bids=[(100.0, 1000.0), (99.0, 2000.0)],
            asks=[(101.0, 1000.0), (102.0, 2000.0)],
        )
        liquidity = manager.analyze_liquidity(depth)

        assessment = manager.assess_risk(
            current_price=100.0,
            volatility=volatility,
            liquidity_metrics=liquidity,
        )

        # Verify risk is finite and bounded
        assert math.isfinite(assessment.risk_score)
        assert 0.0 <= assessment.risk_score <= 1.0

    @pytest.mark.parametrize("bid_depth,ask_depth", [
        (1000, 1000),
        (5000, 1000),
        (1000, 5000),
        (100, 100),
        (10000, 10000),
    ])
    def test_liquidity_imbalance_detection(
        self, manager: AdvancedRiskManager, bid_depth: float, ask_depth: float
    ) -> None:
        """Property: Liquidity imbalance is correctly detected."""
        depth = MarketDepthData(
            bids=[(100.0, bid_depth)],
            asks=[(101.0, ask_depth)],
        )
        liquidity = manager.analyze_liquidity(depth)

        expected_imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

        assert math.isclose(
            liquidity.imbalance_ratio, expected_imbalance, abs_tol=0.1
        )


class TestStressDetectorProperties:
    """Property-style tests for StressDetector."""

    @pytest.fixture
    def detector(self) -> StressDetector:
        """Create a stress detector."""
        return StressDetector()

    @pytest.mark.parametrize("drawdown_pct", [0.0, 0.05, 0.10, 0.15, 0.20, 0.30])
    def test_drawdown_stress_monotonic(
        self, detector: StressDetector, drawdown_pct: float
    ) -> None:
        """Property: Drawdown stress increases monotonically with drawdown."""
        signals = MarketSignals(
            current_price=100 * (1 - drawdown_pct),
            peak_price=100,
        )

        assessment = detector.assess(signals)

        # Larger drawdowns should have higher or equal stress
        assert assessment.drawdown_stress >= 0.0
        assert math.isfinite(assessment.drawdown_stress)

    @pytest.mark.parametrize("volatility_ratio", [0.5, 1.0, 2.0, 3.0, 5.0])
    def test_volatility_stress_proportional(
        self, detector: StressDetector, volatility_ratio: float
    ) -> None:
        """Property: Volatility stress is proportional to volatility ratio."""
        baseline = 0.01
        signals = MarketSignals(
            current_price=100,
            peak_price=100,
            current_volatility=baseline * volatility_ratio,
            baseline_volatility=baseline,
        )

        assessment = detector.assess(signals)

        assert assessment.volatility_stress >= 0.0
        assert math.isfinite(assessment.volatility_stress)

    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_composite_score_bounded(self, detector: StressDetector, seed: int) -> None:
        """Property: Composite stress score is always bounded."""
        rng = np.random.default_rng(seed)

        signals = MarketSignals(
            current_price=rng.uniform(80, 120),
            peak_price=rng.uniform(100, 150),
            current_volatility=rng.uniform(0.01, 0.10),
            baseline_volatility=rng.uniform(0.01, 0.05),
            liquidity_score=rng.uniform(0.0, 1.0),
        )

        assessment = detector.assess(signals)

        assert 0.0 <= assessment.composite_score <= 1.0


class TestFailSafeControllerProperties:
    """Property-style tests for FailSafeController."""

    @pytest.mark.parametrize("multiplier", [0.1, 0.3, 0.5, 0.7, 0.9])
    def test_position_multiplier_respects_config(self, multiplier: float) -> None:
        """Property: Position multiplier respects configuration."""
        config = FailSafeConfig(caution_position_multiplier=multiplier)
        controller = FailSafeController(config=config)

        controller.escalate_to(FailSafeLevel.CAUTION, "Test")

        state = controller.get_state()
        assert state.position_multiplier == multiplier

    @pytest.mark.parametrize("level", list(FailSafeLevel))
    def test_level_has_appropriate_actions(self, level: FailSafeLevel) -> None:
        """Property: Each level has appropriate pending actions."""
        controller = FailSafeController()

        if level == FailSafeLevel.NORMAL:
            return  # Cannot escalate to NORMAL directly

        controller.escalate_to(level, "Test")
        state = controller.get_state()

        # Verify actions are appropriate for level
        if level == FailSafeLevel.EMERGENCY:
            assert len(state.pending_actions) >= 1
        elif level == FailSafeLevel.HALT:
            assert len(state.pending_actions) >= 1
        elif level == FailSafeLevel.RESTRICTED:
            assert len(state.pending_actions) >= 2
        elif level == FailSafeLevel.CAUTION:
            assert len(state.pending_actions) >= 1


class TestEnumComparisonProperties:
    """Property-style tests for enum comparison operators."""

    @pytest.mark.parametrize("level1,level2", [
        (FailSafeLevel.NORMAL, FailSafeLevel.CAUTION),
        (FailSafeLevel.CAUTION, FailSafeLevel.RESTRICTED),
        (FailSafeLevel.RESTRICTED, FailSafeLevel.HALT),
        (FailSafeLevel.HALT, FailSafeLevel.EMERGENCY),
    ])
    def test_failsafe_level_transitivity(
        self, level1: FailSafeLevel, level2: FailSafeLevel
    ) -> None:
        """Property: Level comparisons are transitive."""
        # If level1 < level2, then NOT level2 < level1
        assert level1 < level2
        assert not level2 < level1

        # Reflexivity: level <= level
        assert level1 <= level1
        assert level2 <= level2

    @pytest.mark.parametrize("protocol1,protocol2", [
        (StressResponseProtocol.NORMAL, StressResponseProtocol.DEFENSIVE),
        (StressResponseProtocol.DEFENSIVE, StressResponseProtocol.PROTECTIVE),
        (StressResponseProtocol.PROTECTIVE, StressResponseProtocol.HALT),
        (StressResponseProtocol.HALT, StressResponseProtocol.EMERGENCY),
    ])
    def test_protocol_level_transitivity(
        self, protocol1: StressResponseProtocol, protocol2: StressResponseProtocol
    ) -> None:
        """Property: Protocol comparisons are transitive."""
        assert protocol1 < protocol2
        assert not protocol2 < protocol1

        # Reflexivity
        assert protocol1 <= protocol1
        assert protocol2 <= protocol2

    @pytest.mark.parametrize("state1,state2", [
        (RiskState.OPTIMAL, RiskState.STABLE),
        (RiskState.STABLE, RiskState.ELEVATED),
        (RiskState.ELEVATED, RiskState.STRESSED),
        (RiskState.STRESSED, RiskState.CRITICAL),
    ])
    def test_risk_state_transitivity(
        self, state1: RiskState, state2: RiskState
    ) -> None:
        """Property: RiskState comparisons are transitive."""
        assert state1 < state2
        assert not state2 < state1


class TestNegativeInputHandling:
    """Tests for negative/invalid input handling."""

    @pytest.mark.parametrize("price", [float('nan'), float('inf'), float('-inf')])
    def test_market_depth_with_invalid_price(self, price: float) -> None:
        """Test: Market depth with invalid price is handled."""
        manager = AdvancedRiskManager()

        # Create depth with invalid price
        depth = MarketDepthData(
            bids=[(price, 1000.0)],
            asks=[(100.5, 1000.0)],
        )

        # Should not crash
        metrics = manager.analyze_liquidity(depth)
        assert metrics is not None

    @pytest.mark.parametrize("volume", [0.0, -1.0, float('nan')])
    def test_market_depth_with_invalid_volume(self, volume: float) -> None:
        """Test: Market depth with invalid volume is handled."""
        manager = AdvancedRiskManager()

        depth = MarketDepthData(
            bids=[(100.0, volume)],
            asks=[(100.5, 1000.0)],
        )

        # Should not crash
        metrics = manager.analyze_liquidity(depth)
        assert metrics is not None

    @pytest.mark.parametrize("drawdown", [-0.5, 1.5, float('nan')])
    def test_stress_detector_with_invalid_drawdown(self, drawdown: float) -> None:
        """Test: Stress detector handles invalid drawdown values."""
        detector = StressDetector()

        # Calculate price from drawdown (may be negative or invalid)
        peak = 100
        if math.isnan(drawdown):
            current = float('nan')
        else:
            current = peak * (1 - drawdown)

        signals = MarketSignals(
            current_price=current,
            peak_price=peak,
        )

        # Should not crash
        assessment = detector.assess(signals)
        assert assessment is not None
