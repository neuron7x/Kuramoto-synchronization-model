# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the advanced risk management module.

Comprehensive test coverage for:
- Adaptive risk modulation
- Free energy optimization
- Stress response protocols
- Liquidity analysis
- Scalability and fault tolerance
- Auditing and transparency
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from core.risk_monitoring.advanced_risk_manager import (
    AdvancedRiskAssessment,
    AdvancedRiskConfig,
    AdvancedRiskManager,
    FreeEnergyState,
    LiquidityMetrics,
    MarketDepthData,
    RiskAuditEntry,
    RiskState,
    StressResponseProtocol,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def time_source():
    """Create a mock time source for deterministic testing."""
    current_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def get_time():
        return current_time

    return get_time


@pytest.fixture
def manager(time_source) -> AdvancedRiskManager:
    """Create a basic risk manager for testing."""
    return AdvancedRiskManager(time_source=time_source)


@pytest.fixture
def configured_manager(time_source) -> AdvancedRiskManager:
    """Create a configured risk manager for testing."""
    config = AdvancedRiskConfig(
        volatility_lookback=10,
        liquidity_depth_levels=5,
        spread_stress_threshold_bps=30.0,
        drawdown_elevated_threshold=0.03,
        drawdown_stressed_threshold=0.06,
        drawdown_critical_threshold=0.10,
    )
    return AdvancedRiskManager(config=config, time_source=time_source)


@pytest.fixture
def sample_market_depth() -> MarketDepthData:
    """Create sample market depth data."""
    return MarketDepthData(
        bids=[
            (100.0, 1000.0),
            (99.5, 2000.0),
            (99.0, 3000.0),
            (98.5, 2500.0),
            (98.0, 1500.0),
        ],
        asks=[
            (100.5, 1500.0),
            (101.0, 2500.0),
            (101.5, 2000.0),
            (102.0, 1800.0),
            (102.5, 1200.0),
        ],
        symbol="BTC/USD",
    )


@pytest.fixture
def stressed_market_depth() -> MarketDepthData:
    """Create market depth data representing stressed conditions."""
    return MarketDepthData(
        bids=[
            (100.0, 100.0),  # Very thin bid
            (99.0, 50.0),
        ],
        asks=[
            (105.0, 5000.0),  # Wide spread and heavy ask
            (106.0, 8000.0),
        ],
        symbol="STRESS/TEST",
    )


# =============================================================================
# MarketDepthData Tests
# =============================================================================


class TestMarketDepthData:
    """Tests for MarketDepthData class."""

    def test_get_mid_price_normal(self, sample_market_depth):
        """Test mid-price calculation with normal data."""
        mid = sample_market_depth.get_mid_price()
        assert mid is not None
        assert mid == pytest.approx(100.25, abs=0.01)

    def test_get_mid_price_empty_bids(self):
        """Test mid-price with empty bids."""
        depth = MarketDepthData(
            bids=[],
            asks=[(100.0, 1000.0)],
        )
        assert depth.get_mid_price() is None

    def test_get_mid_price_empty_asks(self):
        """Test mid-price with empty asks."""
        depth = MarketDepthData(
            bids=[(100.0, 1000.0)],
            asks=[],
        )
        assert depth.get_mid_price() is None

    def test_get_spread_bps_normal(self, sample_market_depth):
        """Test spread calculation in basis points."""
        spread = sample_market_depth.get_spread_bps()
        # (100.5 - 100.0) / 100.0 * 10000 = 50 bps
        assert spread == pytest.approx(50.0, abs=0.1)

    def test_get_spread_bps_empty(self):
        """Test spread with empty order book."""
        depth = MarketDepthData(bids=[], asks=[])
        assert depth.get_spread_bps() == float("inf")

    def test_get_spread_bps_wide(self, stressed_market_depth):
        """Test spread with wide market."""
        spread = stressed_market_depth.get_spread_bps()
        # (105.0 - 100.0) / 100.0 * 10000 = 500 bps
        assert spread == pytest.approx(500.0, abs=0.1)


# =============================================================================
# LiquidityMetrics Tests
# =============================================================================


class TestLiquidityMetrics:
    """Tests for LiquidityMetrics class."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = LiquidityMetrics(
            bid_depth_value=1000000.0,
            ask_depth_value=1200000.0,
            imbalance_ratio=-0.1,
            spread_bps=25.0,
            liquidity_score=0.8,
        )
        result = metrics.to_dict()

        assert result["bid_depth_value"] == 1000000.0
        assert result["ask_depth_value"] == 1200000.0
        assert result["imbalance_ratio"] == -0.1
        assert result["spread_bps"] == 25.0
        assert result["liquidity_score"] == 0.8
        assert "timestamp" in result


# =============================================================================
# FreeEnergyState Tests
# =============================================================================


class TestFreeEnergyState:
    """Tests for FreeEnergyState class."""

    def test_default_values(self):
        """Test default state values."""
        state = FreeEnergyState()
        assert state.current_free_energy == 0.0
        assert state.prediction_error == 0.0
        assert state.precision == 1.0
        assert state.is_monotonic is True

    def test_to_dict(self):
        """Test dictionary conversion."""
        state = FreeEnergyState(
            current_free_energy=0.5,
            prediction_error=0.1,
            precision=2.0,
            entropy=0.3,
            stability_metric=0.9,
            descent_rate=0.05,
            is_monotonic=True,
        )
        result = state.to_dict()

        assert result["current_free_energy"] == 0.5
        assert result["prediction_error"] == 0.1
        assert result["precision"] == 2.0
        assert result["entropy"] == 0.3
        assert result["stability_metric"] == 0.9
        assert result["descent_rate"] == 0.05
        assert result["is_monotonic"] is True


# =============================================================================
# AdvancedRiskManager Tests - Initialization
# =============================================================================


class TestAdvancedRiskManagerInit:
    """Tests for AdvancedRiskManager initialization."""

    def test_default_initialization(self, manager):
        """Test default initialization."""
        assert manager.current_protocol == StressResponseProtocol.NORMAL
        assert manager.current_risk_state == RiskState.STABLE
        assert manager.position_multiplier == 1.0

    def test_custom_config(self, time_source):
        """Test initialization with custom config."""
        config = AdvancedRiskConfig(
            volatility_lookback=50,
            spread_stress_threshold_bps=100.0,
        )
        manager = AdvancedRiskManager(config=config, time_source=time_source)

        assert manager.config.volatility_lookback == 50
        assert manager.config.spread_stress_threshold_bps == 100.0

    def test_get_status(self, manager):
        """Test status retrieval."""
        status = manager.get_status()

        assert "risk_state" in status
        assert "protocol" in status
        assert "position_multiplier" in status
        assert "trading_allowed" in status
        assert "free_energy_state" in status
        assert "config" in status


# =============================================================================
# AdvancedRiskManager Tests - Liquidity Analysis
# =============================================================================


class TestLiquidityAnalysis:
    """Tests for liquidity analysis functionality."""

    def test_analyze_liquidity_normal(self, manager, sample_market_depth):
        """Test liquidity analysis with normal market."""
        metrics = manager.analyze_liquidity(sample_market_depth)

        assert metrics.bid_depth_value > 0
        assert metrics.ask_depth_value > 0
        assert -1.0 <= metrics.imbalance_ratio <= 1.0
        assert metrics.spread_bps == pytest.approx(50.0, abs=1.0)
        assert 0.0 <= metrics.liquidity_score <= 1.0
        assert metrics.depth_levels_analyzed == 5

    def test_analyze_liquidity_stressed(self, manager, stressed_market_depth):
        """Test liquidity analysis with stressed market."""
        metrics = manager.analyze_liquidity(stressed_market_depth)

        # Stressed market should have lower liquidity score
        assert metrics.liquidity_score < 0.5
        # Wide spread
        assert metrics.spread_bps > 100.0
        # Heavy imbalance (more asks than bids)
        assert metrics.imbalance_ratio < -0.5

    def test_analyze_liquidity_with_target_size(self, manager, sample_market_depth):
        """Test market impact estimation."""
        metrics = manager.analyze_liquidity(
            sample_market_depth,
            target_trade_size=50000.0,
        )

        assert metrics.market_impact_estimate > 0

    def test_analyze_liquidity_empty_book(self, manager):
        """Test analysis with empty order book."""
        empty_depth = MarketDepthData(bids=[], asks=[])
        metrics = manager.analyze_liquidity(empty_depth)

        assert metrics.bid_depth_value == 0.0
        assert metrics.ask_depth_value == 0.0
        assert metrics.imbalance_ratio == 0.0

    def test_analyze_liquidity_fault_tolerance(self, time_source):
        """Test fault tolerance in liquidity analysis."""
        config = AdvancedRiskConfig(enable_fault_tolerance=True)
        manager = AdvancedRiskManager(config=config, time_source=time_source)

        # Create invalid data that might cause issues
        bad_depth = MarketDepthData(
            bids=[(float("nan"), 1000.0)],
            asks=[(100.0, float("inf"))],
        )

        # Should not raise, should return default
        metrics = manager.analyze_liquidity(bad_depth)
        assert metrics is not None


# =============================================================================
# AdvancedRiskManager Tests - Free Energy
# =============================================================================


class TestFreeEnergyOptimization:
    """Tests for free energy optimization."""

    def test_update_free_energy_initial(self, manager):
        """Test initial free energy update."""
        state = manager.update_free_energy(
            observed_volatility=0.02,
            observed_drawdown=0.05,
        )

        # Free energy can be negative due to entropy term (log of volatility)
        assert math.isfinite(state.current_free_energy)
        assert state.prediction_error >= 0
        assert state.precision > 0
        assert state.is_monotonic is True

    def test_free_energy_monotonicity(self, manager):
        """Test that free energy tends to decrease."""
        # Initialize with some volatility
        manager.update_free_energy(0.05, 0.10)
        initial_fe = manager._fe_state.current_free_energy

        # Simulate improving conditions
        for _ in range(10):
            manager.update_free_energy(0.02, 0.03)

        # Free energy should be lower or equal
        final_fe = manager._fe_state.current_free_energy
        assert final_fe <= initial_fe + 0.1  # Allow small tolerance

    def test_free_energy_precision_adaptation(self, manager):
        """Test precision adaptation based on variance."""
        # Add stable observations
        for _ in range(10):
            manager.update_free_energy(0.02, 0.01)

        stable_precision = manager._fe_state.precision

        # Add volatile observations
        manager2 = AdvancedRiskManager()
        for i in range(10):
            vol = 0.01 if i % 2 == 0 else 0.05
            manager2.update_free_energy(vol, 0.01)

        volatile_precision = manager2._fe_state.precision

        # Stable should have higher precision
        assert stable_precision >= volatile_precision

    def test_free_energy_stability_metric(self, manager):
        """Test stability metric calculation."""
        # Add stable history
        for _ in range(10):
            manager.update_free_energy(0.02, 0.01)

        state = manager._fe_state
        assert state.stability_metric > 0.5  # Should be relatively stable


# =============================================================================
# AdvancedRiskManager Tests - Risk Assessment
# =============================================================================


class TestRiskAssessment:
    """Tests for risk assessment functionality."""

    def test_assess_risk_normal_conditions(self, manager):
        """Test assessment under normal conditions."""
        assessment = manager.assess_risk(
            current_price=100.0,
            peak_price=102.0,
            volatility=0.01,
        )

        assert assessment.risk_state in (RiskState.OPTIMAL, RiskState.STABLE)
        assert assessment.protocol == StressResponseProtocol.NORMAL
        assert assessment.is_trading_allowed is True
        assert assessment.position_multiplier == 1.0

    def test_assess_risk_elevated(self, configured_manager):
        """Test assessment with elevated risk."""
        assessment = configured_manager.assess_risk(
            current_price=97.0,
            peak_price=100.0,  # 3% drawdown
            volatility=0.03,
        )

        # Should detect elevated conditions - risk score should be moderate
        assert assessment.risk_score > 0.1
        assert assessment.drawdown_contribution > 0

    def test_assess_risk_stressed(self, configured_manager):
        """Test assessment under stressed conditions."""
        # First establish baseline volatility
        configured_manager.assess_risk(volatility=0.01)

        # Now assess with high volatility
        assessment = configured_manager.assess_risk(
            current_price=92.0,
            peak_price=100.0,  # 8% drawdown
            volatility=0.05,  # 5x baseline
        )

        # Should detect elevated or higher conditions
        assert assessment.risk_state in (
            RiskState.ELEVATED,
            RiskState.STRESSED,
            RiskState.CRITICAL,
        )
        assert assessment.protocol != StressResponseProtocol.NORMAL
        assert assessment.position_multiplier < 1.0

    def test_assess_risk_critical(self, configured_manager):
        """Test assessment under critical conditions."""
        # Establish baseline
        configured_manager.assess_risk(volatility=0.01)

        assessment = configured_manager.assess_risk(
            current_price=88.0,
            peak_price=100.0,  # 12% drawdown (above critical threshold)
            volatility=0.08,
        )

        assert assessment.risk_state == RiskState.CRITICAL
        assert assessment.protocol in (
            StressResponseProtocol.HALT,
            StressResponseProtocol.PROTECTIVE,
        )
        assert assessment.risk_score >= 0.7

    def test_assess_risk_with_returns(self, manager):
        """Test assessment with return history."""
        returns = np.array([0.01, -0.02, 0.015, -0.005, 0.02])
        assessment = manager.assess_risk(returns=returns)

        assert assessment is not None
        assert len(manager._returns_history) == len(returns)

    def test_assess_risk_with_liquidity(self, manager, sample_market_depth):
        """Test assessment with liquidity metrics."""
        liquidity = manager.analyze_liquidity(sample_market_depth)
        assessment = manager.assess_risk(
            volatility=0.02,
            liquidity_metrics=liquidity,
        )

        assert assessment.liquidity_metrics is not None
        assert assessment.liquidity_contribution >= 0

    def test_assess_risk_generates_recommendations(self, configured_manager):
        """Test that assessment generates recommendations."""
        # Create stressed conditions
        configured_manager.assess_risk(volatility=0.01)

        assessment = configured_manager.assess_risk(
            current_price=85.0,
            peak_price=100.0,
            volatility=0.10,
        )

        assert len(assessment.recommendations) > 0

    def test_assess_risk_fault_tolerance(self, time_source):
        """Test fault tolerance when assessment fails."""
        config = AdvancedRiskConfig(enable_fault_tolerance=True)
        manager = AdvancedRiskManager(config=config, time_source=time_source)

        # First successful assessment
        manager.assess_risk(volatility=0.02)

        # Simulate conditions that might cause issues - NaN volatility
        # The manager should handle this gracefully due to fault tolerance
        assessment = manager.assess_risk(
            volatility=float("nan"),  # Invalid volatility
        )

        # Should still get an assessment (fault tolerance)
        assert assessment is not None
        # The protocol may vary based on the fallback logic
        assert assessment.protocol in (
            StressResponseProtocol.NORMAL,
            StressResponseProtocol.DEFENSIVE,
        )


# =============================================================================
# AdvancedRiskManager Tests - Protocol Management
# =============================================================================


class TestProtocolManagement:
    """Tests for stress response protocol management."""

    def test_escalate_protocol(self, manager):
        """Test protocol escalation."""
        assert manager.current_protocol == StressResponseProtocol.NORMAL

        new_protocol = manager.escalate_protocol("High volatility detected")
        assert new_protocol == StressResponseProtocol.DEFENSIVE

        new_protocol = manager.escalate_protocol("Continued stress")
        assert new_protocol == StressResponseProtocol.PROTECTIVE

    def test_escalate_to_halt(self, manager):
        """Test escalation to halt."""
        manager.escalate_protocol("Step 1")
        manager.escalate_protocol("Step 2")
        manager.escalate_protocol("Step 3")

        assert manager.current_protocol == StressResponseProtocol.HALT
        assert manager.is_trading_allowed() is False

    def test_escalate_to_emergency(self, manager):
        """Test escalation to emergency."""
        for _ in range(4):
            manager.escalate_protocol("Escalate")

        assert manager.current_protocol == StressResponseProtocol.EMERGENCY
        assert manager.position_multiplier == 0.0

    def test_deescalate_protocol(self, manager):
        """Test protocol de-escalation."""
        # First escalate
        manager.escalate_protocol("Escalate")
        manager.escalate_protocol("Escalate more")
        assert manager.current_protocol == StressResponseProtocol.PROTECTIVE

        # Then de-escalate
        new_protocol = manager.deescalate_protocol("Conditions improved")
        assert new_protocol == StressResponseProtocol.DEFENSIVE

        new_protocol = manager.deescalate_protocol("Back to normal")
        assert new_protocol == StressResponseProtocol.NORMAL

    def test_cannot_deescalate_below_normal(self, manager):
        """Test that we can't de-escalate below normal."""
        protocol = manager.deescalate_protocol("Already normal")
        assert protocol == StressResponseProtocol.NORMAL

    def test_is_trading_allowed(self, manager):
        """Test trading allowed check."""
        assert manager.is_trading_allowed() is True

        manager.escalate_protocol("Step 1")
        assert manager.is_trading_allowed() is True

        manager.escalate_protocol("Step 2")
        assert manager.is_trading_allowed() is True

        manager.escalate_protocol("Step 3")  # HALT
        assert manager.is_trading_allowed() is False

    def test_position_adjustment_by_protocol(self, manager):
        """Test position multiplier changes with protocol."""
        assert manager.get_position_adjustment() == 1.0

        manager.escalate_protocol("Defensive")
        assert manager.get_position_adjustment() == 0.7  # Default defensive

        manager.escalate_protocol("Protective")
        assert manager.get_position_adjustment() == 0.3  # Default protective

        manager.escalate_protocol("Halt")
        assert manager.get_position_adjustment() == 0.0


# =============================================================================
# AdvancedRiskManager Tests - Auditing
# =============================================================================


class TestAuditing:
    """Tests for audit trail functionality."""

    def test_audit_trail_on_assessment(self, manager):
        """Test that assessments are audited."""
        manager.assess_risk(volatility=0.02)

        trail = manager.get_audit_trail()
        assert len(trail) == 1
        assert trail[0]["action_type"] == "risk_assessment"

    def test_audit_trail_on_escalation(self, manager):
        """Test that escalations are audited."""
        manager.escalate_protocol("Test escalation")

        trail = manager.get_audit_trail()
        assert len(trail) == 1
        assert trail[0]["action_type"] == "protocol_escalation"
        assert "Test escalation" in str(trail[0]["details"])

    def test_audit_trail_on_deescalation(self, manager):
        """Test that de-escalations are audited."""
        manager.escalate_protocol("Up")
        manager.deescalate_protocol("Down")

        trail = manager.get_audit_trail()
        assert len(trail) == 2
        assert trail[1]["action_type"] == "protocol_deescalation"

    def test_audit_trail_limit(self, manager):
        """Test that audit trail is limited."""
        # Perform many assessments
        for _ in range(100):
            manager.assess_risk(volatility=0.02)

        trail = manager.get_audit_trail()
        assert len(trail) == 100

    def test_audit_trail_filter_by_type(self, manager):
        """Test filtering audit trail by action type."""
        manager.assess_risk(volatility=0.02)
        manager.escalate_protocol("Test")
        manager.assess_risk(volatility=0.02)

        assessments = manager.get_audit_trail(action_type="risk_assessment")
        assert len(assessments) == 2

        escalations = manager.get_audit_trail(action_type="protocol_escalation")
        assert len(escalations) == 1

    def test_audit_entry_contains_free_energy(self, manager):
        """Test that audit entries include free energy state."""
        manager.assess_risk(volatility=0.02)

        trail = manager.get_audit_trail()
        assert trail[0]["free_energy_state"] is not None
        assert "current_free_energy" in trail[0]["free_energy_state"]


# =============================================================================
# AdvancedRiskManager Tests - Reset and State
# =============================================================================


class TestResetAndState:
    """Tests for reset and state management."""

    def test_reset(self, manager):
        """Test reset functionality."""
        # Make some changes
        manager.assess_risk(volatility=0.02)
        manager.escalate_protocol("Test")

        # Reset
        manager.reset()

        assert manager.current_protocol == StressResponseProtocol.NORMAL
        assert manager.current_risk_state == RiskState.STABLE
        assert manager.position_multiplier == 1.0
        assert len(manager.get_audit_trail()) == 0

    def test_get_status_complete(self, manager):
        """Test that status contains all expected fields."""
        manager.assess_risk(volatility=0.02)

        status = manager.get_status()

        required_fields = [
            "risk_state",
            "protocol",
            "position_multiplier",
            "trading_allowed",
            "free_energy_state",
            "baseline_volatility",
            "returns_count",
            "audit_entries_count",
            "consecutive_errors",
            "config",
        ]

        for field in required_fields:
            assert field in status, f"Missing field: {field}"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_complete_risk_workflow(self, manager, sample_market_depth):
        """Test a complete risk management workflow."""
        # 1. Analyze initial liquidity
        liquidity = manager.analyze_liquidity(sample_market_depth)
        assert liquidity.liquidity_score > 0

        # 2. Initial assessment (calm market)
        assessment1 = manager.assess_risk(
            current_price=100.0,
            peak_price=100.0,
            volatility=0.01,
            liquidity_metrics=liquidity,
        )
        assert assessment1.risk_state in (RiskState.OPTIMAL, RiskState.STABLE)
        assert assessment1.is_trading_allowed

        # 3. Market stress begins
        assessment2 = manager.assess_risk(
            current_price=95.0,
            peak_price=100.0,
            volatility=0.05,
        )
        # Risk should have increased
        assert assessment2.risk_score > assessment1.risk_score

        # 4. Further deterioration
        assessment3 = manager.assess_risk(
            current_price=88.0,
            peak_price=100.0,
            volatility=0.10,
        )
        assert assessment3.risk_state in (RiskState.STRESSED, RiskState.CRITICAL)
        assert assessment3.position_multiplier < 1.0

        # 5. Recovery
        for _ in range(5):
            manager.assess_risk(volatility=0.02)

        # De-escalate multiple times if needed
        manager.deescalate_protocol("Conditions normalized")
        manager.deescalate_protocol("Further improvement")

        final_status = manager.get_status()
        # Protocol should be at most protective after de-escalation
        assert final_status["protocol"] in ["normal", "defensive", "protective"]

    def test_audit_trail_transparency(self, manager):
        """Test that all actions are transparently logged."""
        # Perform various actions
        manager.assess_risk(volatility=0.02)
        manager.escalate_protocol("Risk detected")
        manager.assess_risk(volatility=0.05)
        manager.deescalate_protocol("Recovery")
        manager.assess_risk(volatility=0.01)

        trail = manager.get_audit_trail()

        # Should have 5 entries
        assert len(trail) == 5

        # Each entry should have required fields
        for entry in trail:
            assert "entry_id" in entry
            assert "timestamp" in entry
            assert "action_type" in entry
            assert "risk_state" in entry
            assert "protocol" in entry

    def test_concurrent_access_safety(self, time_source):
        """Test thread safety of the manager."""
        import concurrent.futures

        manager = AdvancedRiskManager(time_source=time_source)

        def worker(worker_id: int):
            for _ in range(10):
                manager.assess_risk(volatility=0.02 + worker_id * 0.001)
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, i) for i in range(4)]
            results = [f.result() for f in futures]

        assert all(results)
        # Should have 40 audit entries
        assert len(manager.get_audit_trail()) == 40


# =============================================================================
# RiskAuditEntry Tests
# =============================================================================


class TestRiskAuditEntry:
    """Tests for RiskAuditEntry class."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        entry = RiskAuditEntry(
            entry_id="RISK-00000001",
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            action_type="risk_assessment",
            trigger_source="scheduled",
            risk_state=RiskState.ELEVATED,
            protocol=StressResponseProtocol.DEFENSIVE,
            details={"volatility": 0.05},
            position_adjustment=0.7,
        )

        result = entry.to_dict()

        assert result["entry_id"] == "RISK-00000001"
        assert result["action_type"] == "risk_assessment"
        assert result["risk_state"] == "elevated"
        assert result["protocol"] == "defensive"
        assert result["position_adjustment"] == 0.7


# =============================================================================
# AdvancedRiskAssessment Tests
# =============================================================================


class TestAdvancedRiskAssessment:
    """Tests for AdvancedRiskAssessment class."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        assessment = AdvancedRiskAssessment(
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            risk_state=RiskState.STRESSED,
            protocol=StressResponseProtocol.PROTECTIVE,
            risk_score=0.65,
            volatility_contribution=0.4,
            liquidity_contribution=0.2,
            drawdown_contribution=0.5,
            position_multiplier=0.3,
            recommendations=("Reduce positions", "Monitor closely"),
            is_trading_allowed=True,
        )

        result = assessment.to_dict()

        assert result["risk_state"] == "stressed"
        assert result["protocol"] == "protective"
        assert result["risk_score"] == 0.65
        assert len(result["recommendations"]) == 2
        assert result["is_trading_allowed"] is True


# =============================================================================
# AdvancedRiskConfig Validation Tests
# =============================================================================


class TestAdvancedRiskConfigValidation:
    """Tests for AdvancedRiskConfig validation."""

    def test_valid_default_config(self):
        """Test that default config is valid."""
        config = AdvancedRiskConfig()
        assert config.volatility_lookback == 20
        assert config.drawdown_critical_threshold == 0.15

    def test_invalid_volatility_lookback(self):
        """Test validation of volatility_lookback."""
        with pytest.raises(ValueError, match="volatility_lookback must be >= 2"):
            AdvancedRiskConfig(volatility_lookback=1)

    def test_invalid_liquidity_depth_levels(self):
        """Test validation of liquidity_depth_levels."""
        with pytest.raises(ValueError, match="liquidity_depth_levels must be >= 1"):
            AdvancedRiskConfig(liquidity_depth_levels=0)

    def test_invalid_spread_stress_threshold(self):
        """Test validation of spread_stress_threshold_bps."""
        with pytest.raises(ValueError, match="spread_stress_threshold_bps must be positive"):
            AdvancedRiskConfig(spread_stress_threshold_bps=0)

    def test_invalid_imbalance_threshold(self):
        """Test validation of imbalance_stress_threshold."""
        with pytest.raises(ValueError, match="imbalance_stress_threshold must be in"):
            AdvancedRiskConfig(imbalance_stress_threshold=1.5)

    def test_invalid_drawdown_threshold_order(self):
        """Test validation of drawdown threshold ordering."""
        with pytest.raises(ValueError, match="drawdown thresholds"):
            AdvancedRiskConfig(
                drawdown_elevated_threshold=0.10,
                drawdown_stressed_threshold=0.05,  # Wrong order
            )

    def test_invalid_volatility_ratio_order(self):
        """Test validation of volatility ratio ordering."""
        with pytest.raises(ValueError, match="volatility ratios"):
            AdvancedRiskConfig(
                volatility_elevated_ratio=2.5,
                volatility_stressed_ratio=1.5,  # Wrong order
            )

    def test_invalid_learning_rate(self):
        """Test validation of fe_learning_rate."""
        with pytest.raises(ValueError, match="fe_learning_rate must be in"):
            AdvancedRiskConfig(fe_learning_rate=0)

    def test_invalid_precision_base(self):
        """Test validation of fe_precision_base."""
        with pytest.raises(ValueError, match="fe_precision_base must be positive"):
            AdvancedRiskConfig(fe_precision_base=-1)


# =============================================================================
# StressResponseProtocol Comparison Tests
# =============================================================================


class TestStressResponseProtocolComparison:
    """Tests for StressResponseProtocol comparison operators."""

    def test_protocol_ordering(self):
        """Test that protocols are ordered by severity."""
        assert StressResponseProtocol.NORMAL < StressResponseProtocol.DEFENSIVE
        assert StressResponseProtocol.DEFENSIVE < StressResponseProtocol.PROTECTIVE
        assert StressResponseProtocol.PROTECTIVE < StressResponseProtocol.HALT
        assert StressResponseProtocol.HALT < StressResponseProtocol.EMERGENCY

    def test_protocol_le_ge(self):
        """Test less than or equal and greater than or equal."""
        assert StressResponseProtocol.NORMAL <= StressResponseProtocol.NORMAL
        assert StressResponseProtocol.EMERGENCY >= StressResponseProtocol.EMERGENCY
        assert StressResponseProtocol.HALT <= StressResponseProtocol.EMERGENCY
        assert StressResponseProtocol.PROTECTIVE >= StressResponseProtocol.DEFENSIVE

    def test_protocol_comparison_with_non_protocol(self):
        """Test comparison with non-protocol returns NotImplemented."""
        result = StressResponseProtocol.NORMAL.__lt__("invalid")
        assert result is NotImplemented


# =============================================================================
# Historical Statistics Tests
# =============================================================================


class TestHistoricalStatistics:
    """Tests for historical statistics functionality."""

    def test_get_historical_statistics_empty(self, manager):
        """Test statistics with no data."""
        stats = manager.get_historical_statistics()
        assert stats["data_points"]["returns"] == 0
        assert stats["data_points"]["volatility"] == 0

    def test_get_historical_statistics_with_data(self, manager):
        """Test statistics after assessments."""
        for _ in range(10):
            manager.assess_risk(volatility=0.02)

        stats = manager.get_historical_statistics()
        assert stats["data_points"]["volatility"] == 10
        assert "volatility_stats" in stats
        assert stats["volatility_stats"]["mean"] == pytest.approx(0.02, abs=0.001)

    def test_get_historical_statistics_audit(self, manager):
        """Test audit statistics."""
        manager.assess_risk(volatility=0.02)
        manager.escalate_protocol("Test")
        manager.assess_risk(volatility=0.02)

        stats = manager.get_historical_statistics()
        assert "audit_stats" in stats
        assert stats["audit_stats"]["total_entries"] == 3
        assert "risk_assessment" in stats["audit_stats"]["action_counts"]
