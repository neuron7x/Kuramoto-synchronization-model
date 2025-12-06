# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for Almgren-Chriss optimal execution module."""

from __future__ import annotations

import pytest

from analytics.math_trading.optimal_execution import (
    AlmgrenChrissOptimizer,
    ExecutionSlice,
    OptimalExecutionParams,
    compute_vwap_schedule,
)


class TestOptimalExecutionParams:
    """Tests for OptimalExecutionParams validation."""

    def test_valid_params(self) -> None:
        params = OptimalExecutionParams(
            total_quantity=10000,
            duration_seconds=3600,
            volatility=0.02,
            temporary_impact=0.001,
            permanent_impact=0.0001,
            risk_aversion=1e-6,
        )
        assert params.total_quantity == 10000
        assert params.duration_seconds == 3600

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="total_quantity must be non-zero"):
            OptimalExecutionParams(
                total_quantity=0,
                duration_seconds=3600,
                volatility=0.02,
                temporary_impact=0.001,
                permanent_impact=0.0001,
            )

    def test_negative_duration_raises(self) -> None:
        with pytest.raises(ValueError, match="duration_seconds must be positive"):
            OptimalExecutionParams(
                total_quantity=10000,
                duration_seconds=-100,
                volatility=0.02,
                temporary_impact=0.001,
                permanent_impact=0.0001,
            )

    def test_negative_volatility_raises(self) -> None:
        with pytest.raises(ValueError, match="volatility must be positive"):
            OptimalExecutionParams(
                total_quantity=10000,
                duration_seconds=3600,
                volatility=0,
                temporary_impact=0.001,
                permanent_impact=0.0001,
            )

    def test_negative_impact_raises(self) -> None:
        with pytest.raises(ValueError, match="temporary_impact must be non-negative"):
            OptimalExecutionParams(
                total_quantity=10000,
                duration_seconds=3600,
                volatility=0.02,
                temporary_impact=-0.001,
                permanent_impact=0.0001,
            )


class TestAlmgrenChrissOptimizer:
    """Tests for AlmgrenChrissOptimizer."""

    @pytest.fixture
    def base_params(self) -> OptimalExecutionParams:
        return OptimalExecutionParams(
            total_quantity=10000,
            duration_seconds=3600,
            volatility=0.20,
            temporary_impact=0.001,
            permanent_impact=0.0001,
            risk_aversion=1e-6,
        )

    def test_schedule_generation(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(num_slices=10)

        assert len(result.slices) == 10
        assert all(isinstance(s, ExecutionSlice) for s in result.slices)

    def test_total_quantity_conserved(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(num_slices=20)

        total_traded = sum(s.quantity for s in result.slices)
        assert total_traded == pytest.approx(base_params.total_quantity, rel=1e-6)

    def test_cumulative_tracking(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(num_slices=5)

        cumulative = 0.0
        for s in result.slices:
            cumulative += s.quantity
            assert s.cumulative_quantity == pytest.approx(cumulative, rel=1e-9)

    def test_remaining_quantity(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(num_slices=5)

        for s in result.slices:
            expected_remaining = base_params.total_quantity - s.cumulative_quantity
            assert s.remaining_quantity == pytest.approx(expected_remaining, rel=1e-9)

    def test_time_offsets_increase(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(num_slices=10)

        times = [s.time_offset for s in result.slices]
        assert times == sorted(times)
        assert times[0] == 0.0
        assert times[-1] < base_params.duration_seconds

    def test_urgency_parameter_positive(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        assert optimizer.urgency_parameter > 0

    def test_higher_risk_aversion_front_loads(self) -> None:
        """Higher risk aversion should lead to more front-loaded execution."""
        low_risk = OptimalExecutionParams(
            total_quantity=10000,
            duration_seconds=3600,
            volatility=0.20,
            temporary_impact=0.001,
            permanent_impact=0.0001,
            risk_aversion=1e-8,
        )
        high_risk = OptimalExecutionParams(
            total_quantity=10000,
            duration_seconds=3600,
            volatility=0.20,
            temporary_impact=0.001,
            permanent_impact=0.0001,
            risk_aversion=1e-4,
        )

        low_result = AlmgrenChrissOptimizer(low_risk).compute_schedule(10)
        high_result = AlmgrenChrissOptimizer(high_risk).compute_schedule(10)

        # High risk aversion = execute more at start
        low_first_half = sum(s.quantity for s in low_result.slices[:5])
        high_first_half = sum(s.quantity for s in high_result.slices[:5])

        assert high_first_half > low_first_half

    def test_sell_order_negative_quantities(self) -> None:
        params = OptimalExecutionParams(
            total_quantity=-10000,  # Sell order
            duration_seconds=3600,
            volatility=0.20,
            temporary_impact=0.001,
            permanent_impact=0.0001,
        )
        optimizer = AlmgrenChrissOptimizer(params)
        result = optimizer.compute_schedule(10)

        assert all(s.quantity < 0 for s in result.slices)
        assert sum(s.quantity for s in result.slices) == pytest.approx(-10000, rel=1e-6)

    def test_zero_risk_aversion_linear_schedule(self) -> None:
        params = OptimalExecutionParams(
            total_quantity=10000,
            duration_seconds=3600,
            volatility=0.20,
            temporary_impact=0.001,
            permanent_impact=0.0001,
            risk_aversion=0.0,
        )
        optimizer = AlmgrenChrissOptimizer(params)
        result = optimizer.compute_schedule(10)

        # With zero risk aversion, should be approximately linear (TWAP)
        quantities = [s.quantity for s in result.slices]
        # All slices should be approximately equal
        mean_qty = sum(quantities) / len(quantities)
        for qty in quantities:
            assert qty == pytest.approx(mean_qty, rel=0.01)

    def test_invalid_slices_raises(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        with pytest.raises(ValueError, match="num_slices must be positive"):
            optimizer.compute_schedule(0)

    def test_result_to_dict(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(5)
        d = result.to_dict()

        assert "slices" in d
        assert len(d["slices"]) == 5
        assert "total_expected_cost" in d
        assert "expected_shortfall" in d
        assert "execution_risk" in d

    def test_metrics_non_negative(self, base_params: OptimalExecutionParams) -> None:
        optimizer = AlmgrenChrissOptimizer(base_params)
        result = optimizer.compute_schedule(10)

        assert result.expected_shortfall >= 0
        assert result.execution_risk >= 0
        assert result.total_expected_cost >= 0


class TestVWAPSchedule:
    """Tests for compute_vwap_schedule function."""

    def test_basic_vwap(self) -> None:
        volume_profile = [100, 200, 150, 250, 300]
        slices = compute_vwap_schedule(
            total_quantity=10000,
            volume_profile=volume_profile,
            duration_seconds=3600,
        )

        assert len(slices) == 5
        total = sum(s.quantity for s in slices)
        assert total == pytest.approx(10000, rel=1e-9)

    def test_vwap_proportional(self) -> None:
        volume_profile = [1, 2, 3, 4]  # 10 total
        slices = compute_vwap_schedule(
            total_quantity=1000,
            volume_profile=volume_profile,
            duration_seconds=400,
        )

        assert slices[0].quantity == pytest.approx(100)
        assert slices[1].quantity == pytest.approx(200)
        assert slices[2].quantity == pytest.approx(300)
        assert slices[3].quantity == pytest.approx(400)

    def test_vwap_time_offsets(self) -> None:
        volume_profile = [1, 1, 1, 1]
        slices = compute_vwap_schedule(
            total_quantity=100,
            volume_profile=volume_profile,
            duration_seconds=100,
        )

        assert slices[0].time_offset == 0
        assert slices[1].time_offset == 25
        assert slices[2].time_offset == 50
        assert slices[3].time_offset == 75

    def test_empty_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="volume_profile must not be empty"):
            compute_vwap_schedule(
                total_quantity=1000,
                volume_profile=[],
                duration_seconds=100,
            )

    def test_zero_volume_raises(self) -> None:
        with pytest.raises(ValueError, match="volume_profile must sum to positive"):
            compute_vwap_schedule(
                total_quantity=1000,
                volume_profile=[0, 0, 0],
                duration_seconds=100,
            )

    def test_negative_duration_raises(self) -> None:
        with pytest.raises(ValueError, match="duration_seconds must be positive"):
            compute_vwap_schedule(
                total_quantity=1000,
                volume_profile=[1, 2, 3],
                duration_seconds=-100,
            )
