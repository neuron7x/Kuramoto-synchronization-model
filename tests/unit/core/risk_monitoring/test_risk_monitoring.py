# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Risk Monitoring Framework."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.risk_monitoring.adaptive_thresholds import (
    AdaptiveThresholdCalibrator,
    CalibratedThresholds,
    ThresholdConfig,
)
from core.risk_monitoring.fail_safe import (
    FailSafeAction,
    FailSafeController,
    FailSafeLevel,
)
from core.risk_monitoring.framework import (
    RiskAssessment,
    RiskMonitoringConfig,
    RiskMonitoringFramework,
)
from core.risk_monitoring.performance_tracker import (
    PerformanceTracker,
    PerformanceTrackerConfig,
)
from core.risk_monitoring.stress_detection import (
    MarketSignals,
    StressDetector,
    StressLevel,
)


class TestThresholdConfig:
    """Tests for ThresholdConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ThresholdConfig()
        assert config.base_position_limit == 0.10
        assert config.base_daily_loss_limit == 0.05
        assert config.base_drawdown_limit == 0.15

    def test_invalid_position_limit(self) -> None:
        """Test validation of position limit."""
        with pytest.raises(ValueError, match="base_position_limit"):
            ThresholdConfig(base_position_limit=0)

        with pytest.raises(ValueError, match="base_position_limit"):
            ThresholdConfig(base_position_limit=1.5)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        config = ThresholdConfig()
        d = config.to_dict()
        assert "base_position_limit" in d
        assert d["volatility_lookback"] == 20


class TestAdaptiveThresholdCalibrator:
    """Tests for AdaptiveThresholdCalibrator."""

    def test_initialization(self) -> None:
        """Test calibrator initialization."""
        calibrator = AdaptiveThresholdCalibrator()
        assert calibrator.config is not None
        thresholds = calibrator.get_thresholds()
        assert isinstance(thresholds, CalibratedThresholds)

    def test_update_with_returns(self) -> None:
        """Test calibration with return data."""
        calibrator = AdaptiveThresholdCalibrator()

        # Low volatility returns
        low_vol_returns = np.random.normal(0, 0.01, 30)
        thresholds = calibrator.update(returns=low_vol_returns)

        assert thresholds.adaptation_factor > 0
        assert thresholds.volatility_regime in ["low", "normal", "high"]

    def test_high_volatility_reduces_thresholds(self) -> None:
        """Test that high volatility reduces risk thresholds."""
        calibrator = AdaptiveThresholdCalibrator()

        # First establish baseline with low volatility
        low_vol = np.random.normal(0, 0.01, 30)
        calibrator.update(returns=low_vol)

        # Then inject high volatility
        high_vol = np.random.normal(0, 0.05, 30)
        thresholds = calibrator.update(returns=high_vol)

        # Thresholds should be reduced (adaptation factor < 1)
        assert thresholds.adaptation_factor <= 1.0

    def test_reset(self) -> None:
        """Test calibrator reset."""
        calibrator = AdaptiveThresholdCalibrator()
        calibrator.update(returns=np.random.normal(0, 0.02, 30))
        calibrator.reset()

        status = calibrator.get_status()
        assert status["return_samples"] == 0


class TestStressDetector:
    """Tests for StressDetector."""

    def test_initialization(self) -> None:
        """Test detector initialization."""
        detector = StressDetector()
        assert detector.config is not None
        assert detector.get_last_assessment() is None

    def test_normal_conditions(self) -> None:
        """Test assessment under normal conditions."""
        detector = StressDetector()

        signals = MarketSignals(
            current_price=100,
            peak_price=100,
            current_volatility=0.01,
            baseline_volatility=0.01,
            liquidity_score=0.8,
        )

        assessment = detector.assess(signals)
        assert assessment.stress_level == StressLevel.NORMAL
        assert assessment.composite_score < 0.3

    def test_drawdown_stress(self) -> None:
        """Test stress detection from drawdown."""
        detector = StressDetector()

        signals = MarketSignals(
            current_price=85,  # 15% drawdown
            peak_price=100,
            current_volatility=0.01,
            baseline_volatility=0.01,
        )

        assessment = detector.assess(signals)
        assert assessment.stress_level in [StressLevel.HIGH, StressLevel.CRITICAL]
        assert assessment.drawdown_stress > 0.5

    def test_volatility_stress(self) -> None:
        """Test stress detection from high volatility."""
        detector = StressDetector()

        signals = MarketSignals(
            current_price=100,
            peak_price=100,
            current_volatility=0.04,  # 4x baseline
            baseline_volatility=0.01,
        )

        assessment = detector.assess(signals)
        assert assessment.volatility_stress > 0.5

    def test_liquidity_stress(self) -> None:
        """Test stress detection from low liquidity."""
        detector = StressDetector()

        signals = MarketSignals(
            current_price=100,
            peak_price=100,
            current_volatility=0.01,
            baseline_volatility=0.01,
            liquidity_score=0.1,  # Very low liquidity
            spread_bps=100,  # Wide spread
        )

        assessment = detector.assess(signals)
        assert assessment.liquidity_stress > 0.5

    def test_order_book_imbalance(self) -> None:
        """Test order book imbalance calculation."""
        signals = MarketSignals(
            bid_volume=100,
            ask_volume=50,
        )

        imbalance = signals.get_order_book_imbalance()
        assert imbalance > 0.3  # More bid pressure

    def test_stress_trend(self) -> None:
        """Test stress trend analysis."""
        detector = StressDetector()

        # Create improving trend
        for dd in [0.15, 0.12, 0.09, 0.06, 0.03]:
            signals = MarketSignals(
                current_price=100 - dd * 100,
                peak_price=100,
            )
            detector.assess(signals)

        trend = detector.get_stress_trend()
        assert trend == "improving"


class TestPerformanceTracker:
    """Tests for PerformanceTracker."""

    def test_initialization(self) -> None:
        """Test tracker initialization."""
        tracker = PerformanceTracker()
        metrics = tracker.get_metrics()

        assert metrics.total_return == 0.0
        assert tracker.config.initial_capital == 100_000.0

    def test_update_equity(self) -> None:
        """Test equity updates."""
        config = PerformanceTrackerConfig(initial_capital=100_000)
        tracker = PerformanceTracker(config)

        tracker.update_equity(102_000)
        tracker.update_equity(101_500)

        metrics = tracker.get_metrics()
        assert metrics.total_return == 1_500
        assert metrics.total_return_pct == 1.5

    def test_drawdown_calculation(self) -> None:
        """Test drawdown calculation."""
        tracker = PerformanceTracker(PerformanceTrackerConfig(initial_capital=100_000))

        tracker.update_equity(110_000)  # New peak
        tracker.update_equity(99_000)  # Drawdown

        metrics = tracker.get_metrics()
        # Drawdown from 110k to 99k = 10%
        assert metrics.current_drawdown > 0.09
        assert metrics.max_drawdown_pct > 9.0

    def test_sharpe_ratio(self) -> None:
        """Test Sharpe ratio calculation."""
        tracker = PerformanceTracker()

        # Generate some returns
        np.random.seed(42)
        for _ in range(50):
            ret = np.random.normal(0.001, 0.02)  # Positive drift
            tracker.record_return(ret)

        metrics = tracker.get_metrics()
        # Should have a Sharpe ratio (positive due to positive drift)
        assert metrics.sharpe_ratio is not None

    def test_performance_report(self) -> None:
        """Test performance report generation."""
        tracker = PerformanceTracker()

        for i in range(30):
            tracker.update_equity(100_000 + i * 500)

        report = tracker.generate_report()
        assert report.metrics is not None
        assert len(report.recommendations) >= 0

    def test_reset(self) -> None:
        """Test tracker reset."""
        tracker = PerformanceTracker()
        tracker.update_equity(110_000)
        tracker.reset(initial_capital=50_000)

        status = tracker.get_status()
        assert status["initial_capital"] == 50_000
        assert status["total_periods"] == 0


class TestFailSafeController:
    """Tests for FailSafeController."""

    def test_initialization(self) -> None:
        """Test controller initialization."""
        controller = FailSafeController()
        state = controller.get_state()

        assert state.level == FailSafeLevel.NORMAL
        assert state.active is False
        assert state.position_multiplier == 1.0

    def test_escalation(self) -> None:
        """Test escalation to higher levels."""
        controller = FailSafeController()

        state = controller.escalate_to(FailSafeLevel.CAUTION, "Test escalation", source="test")

        assert state.level == FailSafeLevel.CAUTION
        assert state.active is True
        assert state.position_multiplier < 1.0

    def test_kill_switch(self) -> None:
        """Test kill-switch activation."""
        controller = FailSafeController()

        state = controller.activate_kill_switch("Emergency stop")

        assert state.level == FailSafeLevel.HALT
        assert controller.is_trading_allowed() is False
        assert state.allow_new_orders is False

    def test_deactivation(self) -> None:
        """Test fail-safe deactivation."""
        controller = FailSafeController()

        controller.escalate_to(FailSafeLevel.CAUTION, "Test")
        state = controller.deactivate(source="operator", reason="Test reset")

        assert state.level == FailSafeLevel.NORMAL
        assert state.active is False

    def test_step_down(self) -> None:
        """Test step-down mechanism."""
        controller = FailSafeController()

        controller.escalate_to(FailSafeLevel.RESTRICTED, "Test")
        state = controller.step_down(source="operator", reason="Improved")

        assert state.level == FailSafeLevel.CAUTION

    def test_stress_reporting(self) -> None:
        """Test stress level reporting."""
        from datetime import timedelta

        # Create a time source that can be advanced
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time_offset = [0]  # Use list to allow mutation in closure

        def time_source() -> datetime:
            return base_time + timedelta(seconds=time_offset[0])

        controller = FailSafeController(time_source=time_source)

        # Report sustained high stress over 2 minutes (70 reports, 2 seconds apart)
        for i in range(70):
            time_offset[0] = i * 2
            controller.report_stress("high", source="test")

        state = controller.get_state()
        # Should have escalated due to sustained stress (threshold is 60 seconds)
        assert state.level >= FailSafeLevel.CAUTION

    def test_action_acknowledgement(self) -> None:
        """Test action acknowledgement."""
        controller = FailSafeController()

        controller.escalate_to(FailSafeLevel.CAUTION, "Test")
        state = controller.get_state()

        if FailSafeAction.REDUCE_POSITIONS in state.pending_actions:
            controller.acknowledge_action(FailSafeAction.REDUCE_POSITIONS)
            new_state = controller.get_state()
            assert FailSafeAction.REDUCE_POSITIONS not in new_state.pending_actions


class TestRiskMonitoringFramework:
    """Tests for RiskMonitoringFramework."""

    @pytest.fixture
    def framework(self, tmp_path: Path) -> RiskMonitoringFramework:
        """Create a framework instance."""
        config = RiskMonitoringConfig(
            storage_path=tmp_path / "risk_data",
            initial_capital=100_000,
        )
        return RiskMonitoringFramework(config)

    def test_initialization(self, framework: RiskMonitoringFramework) -> None:
        """Test framework initialization."""
        assert framework.config is not None
        assert framework.threshold_calibrator is not None
        assert framework.stress_detector is not None
        assert framework.compliance is not None
        assert framework.performance is not None
        assert framework.fail_safe is not None

    def test_market_data_update(self, framework: RiskMonitoringFramework) -> None:
        """Test market data update."""
        returns = np.random.normal(0, 0.02, 30)
        volumes = np.random.uniform(1000, 2000, 30)

        thresholds = framework.update_market_data(
            returns=returns,
            volumes=volumes,
        )

        assert thresholds is not None
        assert thresholds.adaptation_factor > 0

    def test_equity_update(self, framework: RiskMonitoringFramework) -> None:
        """Test equity update."""
        metrics = framework.update_equity(105_000)

        assert metrics is not None
        assert metrics.total_return == 5_000

    def test_risk_assessment(self, framework: RiskMonitoringFramework) -> None:
        """Test comprehensive risk assessment."""
        signals = MarketSignals(
            current_price=95,
            peak_price=100,
            current_volatility=0.02,
            baseline_volatility=0.01,
        )

        assessment = framework.assess(signals, equity=98_000)

        assert isinstance(assessment, RiskAssessment)
        assert assessment.stress_assessment is not None
        assert assessment.performance is not None
        assert 0 <= assessment.risk_score <= 1

    def test_trading_allowed(self, framework: RiskMonitoringFramework) -> None:
        """Test trading permission check."""
        assert framework.is_trading_allowed() is True

        # Activate kill-switch
        if framework.fail_safe:
            framework.fail_safe.activate_kill_switch("Test")

        assert framework.is_trading_allowed() is False

    def test_position_multiplier(self, framework: RiskMonitoringFramework) -> None:
        """Test position multiplier calculation."""
        multiplier = framework.get_position_multiplier()

        assert 0 <= multiplier <= 1.5

    def test_status(self, framework: RiskMonitoringFramework) -> None:
        """Test status retrieval."""
        status = framework.get_status()

        assert "framework_enabled" in status
        assert "thresholds" in status
        assert "stress" in status
        assert "compliance" in status
        assert "performance" in status
        assert "fail_safe" in status

    def test_reset(self, framework: RiskMonitoringFramework) -> None:
        """Test framework reset."""
        framework.update_equity(110_000)
        framework.reset()

        if framework.performance:
            metrics = framework.performance.get_metrics()
            assert metrics.total_return == 0


class TestIntegration:
    """Integration tests for complete risk monitoring workflow."""

    @pytest.fixture
    def framework(self, tmp_path: Path) -> RiskMonitoringFramework:
        """Create framework for integration tests."""
        return RiskMonitoringFramework(
            RiskMonitoringConfig(
                storage_path=tmp_path / "integration_test",
                initial_capital=100_000,
                auto_escalate=True,
            )
        )

    def test_stress_to_failsafe_escalation(self, framework: RiskMonitoringFramework) -> None:
        """Test that stress triggers fail-safe escalation."""
        # Simulate market crash with critical drawdown
        signals = MarketSignals(
            current_price=80,  # 20% drawdown is critical
            peak_price=100,
            current_volatility=0.04,  # 4x volatility
            baseline_volatility=0.01,
        )

        assessment = framework.assess(signals, equity=80_000)

        # Check that stress was detected
        assert assessment.stress_assessment is not None
        assert assessment.stress_assessment.stress_level in [
            StressLevel.HIGH,
            StressLevel.CRITICAL,
        ]

        # Check that action is required
        assert assessment.requires_action is True
        assert assessment.risk_score > 0.3

    def test_complete_assessment_cycle(self, framework: RiskMonitoringFramework) -> None:
        """Test complete assessment cycle."""
        # 1. Update market data
        returns = np.random.normal(0, 0.01, 30)
        framework.update_market_data(returns=returns)

        # 2. Assess risk with equity update
        signals = MarketSignals(
            current_price=102,
            peak_price=102,
            current_volatility=0.01,
            baseline_volatility=0.01,
            liquidity_score=0.8,
        )
        assessment = framework.assess(signals, equity=102_000)

        # 3. Check results
        assert assessment.stress_assessment is not None
        assert assessment.thresholds is not None
        assert assessment.performance is not None
        assert assessment.fail_safe_state is not None

        # Normal conditions should not require action
        if assessment.risk_score < 0.3:
            assert not assessment.requires_action

    def test_compliance_audit_trail(self, framework: RiskMonitoringFramework) -> None:
        """Test compliance audit trail."""
        # Perform several operations
        framework.update_equity(105_000)
        framework.assess(MarketSignals(current_price=100, peak_price=100))

        # Check compliance status
        if framework.compliance:
            status = framework.compliance.get_compliance_status()
            assert status["total_audit_entries"] > 0
