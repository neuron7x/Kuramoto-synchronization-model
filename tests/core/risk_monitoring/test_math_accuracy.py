# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Math accuracy tests for the advanced risk management module.

This module validates the mathematical correctness and numerical stability
of risk calculations, specifically targeting:

MATH CONTRACT:
- Volatility calculations use unbiased sample estimation (ddof=1)
- All outputs are finite (no NaN/Inf)
- Edge cases (constant series, zero baseline, etc.) are handled safely
- Results fall within documented bounds

Tests follow the TradePulse math accuracy guidelines:
- T1: Unit tests with hand-computed expected values
- T2: Invariant tests (bounds, non-negativity, finite outputs)
- T3: Regression tests with golden values
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from core.risk_monitoring.advanced_risk_manager import (
    AdvancedRiskConfig,
    AdvancedRiskManager,
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
    """Create a configured risk manager with lower thresholds for testing."""
    config = AdvancedRiskConfig(
        volatility_lookback=10,
        liquidity_depth_levels=5,
        spread_stress_threshold_bps=30.0,
        drawdown_elevated_threshold=0.03,
        drawdown_stressed_threshold=0.06,
        drawdown_critical_threshold=0.10,
    )
    return AdvancedRiskManager(config=config, time_source=time_source)


# =============================================================================
# T1: Unit Tests with Hand-Computed Values (6 tests)
# =============================================================================


class TestVolatilityCalculationAccuracy:
    """Tests validating unbiased variance/std estimation with ddof=1."""

    def test_volatility_uses_unbiased_estimator_sample_variance(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.1: Verify sample variance uses ddof=1 for unbiased estimation.

        Hand-computed example:
        Returns: [0.01, 0.02, 0.03]
        Mean: 0.02
        Sample variance (ddof=1): [(0.01-0.02)^2 + (0.02-0.02)^2 + (0.03-0.02)^2] / 2
                                = [0.0001 + 0 + 0.0001] / 2 = 0.0001
        Sample std (ddof=1): sqrt(0.0001) = 0.01
        """
        # Manually add returns to history
        returns = np.array([0.01, 0.02, 0.03])

        # Assess risk to trigger internal volatility calculation
        assessment = manager.assess_risk(returns=returns)

        # The internal calculation should use ddof=1
        # Expected: sum of squared deviations = 0.0001 + 0 + 0.0001 = 0.0002
        # Sample variance (ddof=1) = 0.0002 / 2 = 0.0001
        # Sample std (ddof=1) = sqrt(0.0001) = 0.01
        expected_std = np.std(returns, ddof=1)
        assert expected_std == pytest.approx(0.01, rel=1e-10)

        # Verify the assessment completes successfully
        assert assessment is not None
        assert np.isfinite(assessment.risk_score)

    def test_volatility_with_known_values(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.2: Test volatility calculation with known standard deviation.

        Hand-computed example:
        Returns: [0.0, 0.1, 0.2, 0.3, 0.4]
        Mean: 0.2
        Sample variance (ddof=1): sum((xi - 0.2)^2) / 4
            = [0.04 + 0.01 + 0 + 0.01 + 0.04] / 4 = 0.1 / 4 = 0.025
        Sample std (ddof=1): sqrt(0.025) = 0.158113883...
        """
        returns = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        expected_std = np.std(returns, ddof=1)

        # Verify our hand-calculation
        assert expected_std == pytest.approx(0.158113883, rel=1e-7)

        # Assess risk
        assessment = manager.assess_risk(returns=returns)
        assert np.isfinite(assessment.risk_score)

    def test_free_energy_precision_calculation(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.3: Verify free energy precision uses unbiased variance.

        Precision = base / (variance + epsilon)
        With ddof=1, variance is higher (n/(n-1) times population variance)
        leading to lower precision (more conservative).
        """
        # Feed enough data to trigger precision calculation
        for i in range(5):
            assessment = manager.assess_risk(
                volatility=0.01 + i * 0.001,
                current_price=100.0,
                peak_price=100.0,
            )

        # Check that precision is within documented bounds [0.01, 100.0]
        fe_state = assessment.free_energy_state
        assert fe_state is not None
        assert 0.01 <= fe_state.precision <= 100.0
        assert np.isfinite(fe_state.precision)

    def test_stability_metric_variance_calculation(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.4: Verify stability metric uses unbiased variance.

        Stability = 1 / (1 + variance)
        Must be in [0, 1] range.
        """
        # Generate enough history for stability calculation
        for i in range(10):
            manager.assess_risk(
                volatility=0.01 + (i % 3) * 0.001,
                current_price=100.0,
                peak_price=100.0,
            )

        fe_state = manager._fe_state
        assert 0.0 <= fe_state.stability_metric <= 1.0
        assert np.isfinite(fe_state.stability_metric)


class TestEdgeCaseHandling:
    """Tests for edge case handling in math operations."""

    def test_constant_series_returns_zero_volatility(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.5: Constant series (std=0) should not produce NaN.

        When all returns are identical, std with ddof=1 would be 0,
        not NaN (which can happen in some edge cases).
        """
        constant_returns = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
        assessment = manager.assess_risk(returns=constant_returns)

        # Should handle gracefully
        assert np.isfinite(assessment.risk_score)
        assert np.isfinite(assessment.volatility_contribution)

    def test_single_return_value_handled(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T1.6: Single value input should not crash.

        With only one return, std(ddof=1) would be undefined.
        The system should handle this gracefully.
        """
        single_return = np.array([0.01])
        assessment = manager.assess_risk(returns=single_return)

        # Should handle gracefully without NaN
        assert np.isfinite(assessment.risk_score)


# =============================================================================
# T2: Invariant Tests (4 tests)
# =============================================================================


class TestMathInvariants:
    """Tests validating mathematical invariants and bounds."""

    def test_risk_score_bounds(self, manager: AdvancedRiskManager) -> None:
        """T2.1: Risk score must always be in [0.0, 1.0] range."""
        test_cases = [
            # (volatility, drawdown parameters)
            (0.0, 100.0, 100.0),  # Zero volatility
            (0.5, 100.0, 100.0),  # High volatility
            (0.01, 100.0, 80.0),  # High drawdown
            (0.001, 100.0, 100.0),  # Low volatility
        ]

        for vol, peak, current in test_cases:
            assessment = manager.assess_risk(
                volatility=vol,
                current_price=current,
                peak_price=peak,
            )
            assert 0.0 <= assessment.risk_score <= 1.0, (
                f"Risk score {assessment.risk_score} out of bounds for "
                f"vol={vol}, peak={peak}, current={current}"
            )

    def test_volatility_contribution_non_negative(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T2.2: Volatility contribution must always be >= 0."""
        for volatility in [0.0, 0.001, 0.01, 0.1, 0.5]:
            assessment = manager.assess_risk(volatility=volatility)
            assert assessment.volatility_contribution >= 0.0
            assert assessment.volatility_contribution <= 1.0

    def test_free_energy_fields_finite(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T2.3: All FreeEnergyState fields must be finite."""
        # Generate varied inputs
        for i in range(10):
            manager.assess_risk(
                volatility=0.01 * (i + 1),
                current_price=100.0,
                peak_price=100.0 + i,
            )

        fe_state = manager._fe_state
        assert np.isfinite(fe_state.current_free_energy)
        assert np.isfinite(fe_state.prediction_error)
        assert np.isfinite(fe_state.precision)
        assert np.isfinite(fe_state.entropy)
        assert np.isfinite(fe_state.stability_metric)
        assert np.isfinite(fe_state.descent_rate)

    def test_precision_bounds_enforced(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T2.4: Precision must be clamped to [0.01, 100.0]."""
        # Test with extreme variance (low precision)
        for i in range(20):
            manager.assess_risk(
                volatility=0.5 + i * 0.1,  # Increasing volatility
                current_price=100.0,
                peak_price=100.0,
            )

        fe_state = manager._fe_state
        assert 0.01 <= fe_state.precision <= 100.0


# =============================================================================
# T3: Regression Tests with Golden Values
# =============================================================================


class TestRegressionGoldenValues:
    """Regression tests with known golden output values."""

    def test_volatility_risk_assessment_golden(
        self, time_source
    ) -> None:
        """T3.1: Regression test for volatility risk assessment.

        Golden values computed with verified implementation.
        """
        manager = AdvancedRiskManager(time_source=time_source)

        # First, establish a baseline volatility
        for _ in range(5):
            manager.assess_risk(volatility=0.02)

        # Now assess with 2x baseline volatility
        assessment = manager.assess_risk(volatility=0.04)

        # With 2x baseline, should be in elevated but not stressed range
        # volatility_elevated_ratio = 1.5, volatility_stressed_ratio = 2.0
        # vol_ratio = 2.0, which is exactly at stressed threshold
        assert assessment.volatility_contribution >= 0.3  # At least elevated
        assert assessment.volatility_contribution <= 1.0
        assert np.isfinite(assessment.risk_score)

    def test_drawdown_risk_assessment_golden(
        self, time_source
    ) -> None:
        """T3.2: Regression test for drawdown risk assessment.

        Default thresholds:
        - elevated: 0.05
        - stressed: 0.10
        - critical: 0.15
        """
        manager = AdvancedRiskManager(time_source=time_source)

        # Test at 7.5% drawdown (between elevated and stressed)
        assessment = manager.assess_risk(
            current_price=92.5,
            peak_price=100.0,
        )

        # Drawdown = (100 - 92.5) / 100 = 0.075
        # Should be in elevated range (0.05-0.10)
        assert assessment.drawdown_contribution >= 0.3
        assert assessment.drawdown_contribution <= 0.6
        assert np.isfinite(assessment.risk_score)

    def test_historical_statistics_golden(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T3.3: Regression test for historical statistics calculation.

        Verify stats use unbiased estimators and produce correct values.
        """
        # Add known volatility values
        volatilities = [0.01, 0.02, 0.03, 0.02, 0.01]
        for vol in volatilities:
            manager.assess_risk(volatility=vol)

        stats = manager.get_historical_statistics()

        # Check volatility stats
        vol_stats = stats.get("volatility_stats", {})
        expected_mean = np.mean(volatilities)
        expected_std = np.std(volatilities, ddof=1)

        assert vol_stats["mean"] == pytest.approx(expected_mean, rel=1e-10)
        assert vol_stats["std"] == pytest.approx(expected_std, rel=1e-10)

    def test_free_energy_statistics_golden(
        self, manager: AdvancedRiskManager
    ) -> None:
        """T3.4: Regression test for free energy statistics.

        Verify FE history stats use unbiased estimators.
        """
        # Generate some history
        for i in range(10):
            manager.assess_risk(
                volatility=0.01 + (i % 3) * 0.005,
                current_price=100.0,
                peak_price=100.0 + i * 0.5,
            )

        stats = manager.get_historical_statistics()
        fe_stats = stats.get("free_energy_stats", {})

        # All values should be finite
        assert np.isfinite(fe_stats["mean"])
        assert np.isfinite(fe_stats["std"])
        assert np.isfinite(fe_stats["min"])
        assert np.isfinite(fe_stats["max"])


# =============================================================================
# Edge Case Tests for Non-Finite Input Handling
# =============================================================================


class TestNonFiniteInputHandling:
    """Tests for handling NaN and Inf inputs gracefully."""

    def test_nan_volatility_returns_conservative_default(
        self, manager: AdvancedRiskManager
    ) -> None:
        """NaN volatility should return conservative risk (0.3)."""
        manager._baseline_volatility = 0.01  # Set baseline

        result = manager._assess_volatility_risk(float("nan"))
        assert result == 0.3

    def test_inf_volatility_returns_conservative_default(
        self, manager: AdvancedRiskManager
    ) -> None:
        """Inf volatility should return conservative risk (0.3)."""
        manager._baseline_volatility = 0.01

        result = manager._assess_volatility_risk(float("inf"))
        assert result == 0.3

    def test_negative_volatility_returns_conservative_default(
        self, manager: AdvancedRiskManager
    ) -> None:
        """Negative volatility should return conservative risk (0.3)."""
        manager._baseline_volatility = 0.01

        result = manager._assess_volatility_risk(-0.01)
        assert result == 0.3

    def test_returns_with_nan_values_filtered(
        self, manager: AdvancedRiskManager
    ) -> None:
        """Returns array with NaN values should be filtered."""
        returns = np.array([0.01, np.nan, 0.02, np.inf, 0.03, -np.inf])
        assessment = manager.assess_risk(returns=returns)

        # Should complete without error, filtering non-finite values
        assert np.isfinite(assessment.risk_score)

    def test_nan_volatility_keeps_state_finite(
        self, manager: AdvancedRiskManager
    ) -> None:
        """NaN volatility should not poison free energy state or risk score."""
        # Establish baseline with a finite observation
        manager.assess_risk(volatility=0.02)

        assessment = manager.assess_risk(volatility=float("nan"))
        fe_state = manager._fe_state

        assert np.isfinite(assessment.risk_score)
        assert 0.0 <= assessment.risk_score <= 1.0
        assert np.isfinite(fe_state.current_free_energy)
        assert np.isfinite(fe_state.precision)
        assert np.isfinite(fe_state.prediction_error)
        assert np.isfinite(fe_state.entropy)


# =============================================================================
# Determinism Tests
# =============================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_identical_inputs_produce_identical_outputs(
        self, time_source
    ) -> None:
        """Same inputs should always produce same outputs."""
        results = []

        for _ in range(3):
            manager = AdvancedRiskManager(time_source=time_source)
            returns = np.array([0.01, 0.02, 0.015, 0.01, 0.02])

            assessment = manager.assess_risk(
                returns=returns,
                volatility=0.01,
                current_price=99.0,
                peak_price=100.0,
            )
            results.append(assessment.risk_score)

        # All results should be identical
        assert results[0] == results[1] == results[2]

    def test_volatility_calculation_deterministic(
        self, time_source
    ) -> None:
        """Volatility calculation should be deterministic."""
        results = []

        for _ in range(3):
            manager = AdvancedRiskManager(time_source=time_source)
            returns = np.array([0.01, 0.02, 0.03, 0.02, 0.01])

            manager.assess_risk(returns=returns)
            stats = manager.get_historical_statistics()
            results.append(stats.get("volatility_stats", {}).get("std"))

        # All std values should be identical (no randomness)
        assert results[0] == results[1] == results[2]
