# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for Kelly criterion module."""

from __future__ import annotations

import numpy as np
import pytest

from analytics.math_trading.kelly_criterion import (
    KellyCriterion,
    KellyParams,
    MultiAssetKelly,
    MultiAssetKellyParams,
    MultiAssetKellyResult,
    kelly_from_edge_variance,
)


class TestKellyParams:
    """Tests for KellyParams validation."""

    def test_valid_params(self) -> None:
        params = KellyParams(
            win_probability=0.6,
            win_loss_ratio=1.5,
        )
        assert params.win_probability == 0.6
        assert params.win_loss_ratio == 1.5

    def test_probability_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="win_probability must be between 0 and 1"):
            KellyParams(win_probability=0, win_loss_ratio=1.0)

    def test_probability_one_raises(self) -> None:
        with pytest.raises(ValueError, match="win_probability must be between 0 and 1"):
            KellyParams(win_probability=1.0, win_loss_ratio=1.0)

    def test_negative_ratio_raises(self) -> None:
        with pytest.raises(ValueError, match="win_loss_ratio must be positive"):
            KellyParams(win_probability=0.5, win_loss_ratio=-1.0)

    def test_negative_max_fraction_raises(self) -> None:
        with pytest.raises(ValueError, match="max_fraction must be positive"):
            KellyParams(win_probability=0.5, win_loss_ratio=1.0, max_fraction=0)

    def test_invalid_fractional_kelly(self) -> None:
        with pytest.raises(ValueError, match="fractional_kelly must be between 0 and 1"):
            KellyParams(win_probability=0.5, win_loss_ratio=1.0, fractional_kelly=0)


class TestKellyCriterion:
    """Tests for KellyCriterion single-asset calculator."""

    @pytest.fixture
    def kelly(self) -> KellyCriterion:
        return KellyCriterion()

    def test_standard_kelly_formula(self, kelly: KellyCriterion) -> None:
        """Test the classic Kelly formula: f* = (bp - q) / b"""
        params = KellyParams(
            win_probability=0.6,
            win_loss_ratio=1.0,  # Even odds
        )
        result = kelly.compute(params)

        # f* = (1.0 * 0.6 - 0.4) / 1.0 = 0.2
        assert result.full_kelly == pytest.approx(0.2)
        assert result.optimal_fraction == pytest.approx(0.2)

    def test_high_edge_scenario(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.7,
            win_loss_ratio=2.0,
        )
        result = kelly.compute(params)

        # f* = (2.0 * 0.7 - 0.3) / 2.0 = 0.55
        assert result.full_kelly == pytest.approx(0.55)

    def test_no_edge_zero_kelly(self, kelly: KellyCriterion) -> None:
        """50/50 with even odds = zero edge"""
        params = KellyParams(
            win_probability=0.5,
            win_loss_ratio=1.0,
        )
        result = kelly.compute(params)

        assert result.full_kelly == pytest.approx(0.0)
        assert result.edge == pytest.approx(0.0)

    def test_negative_edge_clamped_to_zero(self, kelly: KellyCriterion) -> None:
        """Losing strategy should return 0 bet"""
        params = KellyParams(
            win_probability=0.4,
            win_loss_ratio=1.0,  # Negative edge
        )
        result = kelly.compute(params)

        assert result.full_kelly == pytest.approx(-0.2)
        assert result.optimal_fraction == 0.0  # Clamped

    def test_fractional_kelly(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.6,
            win_loss_ratio=1.0,
            fractional_kelly=0.5,  # Half Kelly
        )
        result = kelly.compute(params)

        assert result.full_kelly == pytest.approx(0.2)
        assert result.optimal_fraction == pytest.approx(0.1)

    def test_max_fraction_limit(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.8,
            win_loss_ratio=3.0,
            max_fraction=0.25,
        )
        result = kelly.compute(params)

        # Full Kelly would be much higher, but capped
        assert result.optimal_fraction == 0.25
        assert result.full_kelly > 0.25

    def test_edge_calculation(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.55,
            win_loss_ratio=1.0,
        )
        result = kelly.compute(params)

        # Edge = p*b - q = 0.55*1.0 - 0.45 = 0.10
        assert result.edge == pytest.approx(0.10)

    def test_growth_rate_positive(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.6,
            win_loss_ratio=1.5,
        )
        result = kelly.compute(params)

        assert result.growth_rate > 0

    def test_max_drawdown_estimate(self, kelly: KellyCriterion) -> None:
        params = KellyParams(
            win_probability=0.6,
            win_loss_ratio=1.0,
        )
        result = kelly.compute(params)

        assert result.max_drawdown_estimate > 0
        assert result.max_drawdown_estimate < 1

    def test_result_to_dict(self, kelly: KellyCriterion) -> None:
        params = KellyParams(win_probability=0.6, win_loss_ratio=1.0)
        result = kelly.compute(params)
        d = result.to_dict()

        assert "optimal_fraction" in d
        assert "full_kelly" in d
        assert "edge" in d
        assert "growth_rate" in d


class TestMultiAssetKellyParams:
    """Tests for MultiAssetKellyParams validation."""

    def test_valid_params(self) -> None:
        mu = np.array([0.10, 0.08])
        sigma = np.array([[0.04, 0.01], [0.01, 0.03]])
        params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("A", "B"),
        )
        assert len(params.asset_names) == 2

    def test_return_dimension_mismatch(self) -> None:
        mu = np.array([0.10, 0.08, 0.12])  # 3 assets
        sigma = np.array([[0.04, 0.01], [0.01, 0.03]])  # 2x2
        with pytest.raises(ValueError, match="expected_returns dimension mismatch"):
            MultiAssetKellyParams(
                expected_returns=mu,
                covariance_matrix=sigma,
                asset_names=("A", "B"),
            )

    def test_covariance_dimension_mismatch(self) -> None:
        mu = np.array([0.10, 0.08])
        sigma = np.array([[0.04, 0.01, 0], [0.01, 0.03, 0], [0, 0, 0.02]])
        with pytest.raises(ValueError, match="covariance_matrix dimension mismatch"):
            MultiAssetKellyParams(
                expected_returns=mu,
                covariance_matrix=sigma,
                asset_names=("A", "B"),
            )


class TestMultiAssetKelly:
    """Tests for MultiAssetKelly optimizer."""

    @pytest.fixture
    def simple_params(self) -> MultiAssetKellyParams:
        mu = np.array([0.10, 0.08, 0.12])
        sigma = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.03, 0.01],
            [0.02, 0.01, 0.05],
        ])
        return MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("AAPL", "GOOG", "MSFT"),
        )

    def test_optimization_returns_result(
        self, simple_params: MultiAssetKellyParams
    ) -> None:
        kelly = MultiAssetKelly()
        result = kelly.optimize(simple_params)

        assert isinstance(result, MultiAssetKellyResult)
        assert len(result.optimal_positions) == 3

    def test_leverage_constraint_respected(self) -> None:
        mu = np.array([0.15, 0.15, 0.15])  # High returns
        sigma = np.array([
            [0.01, 0, 0],
            [0, 0.01, 0],
            [0, 0, 0.01],
        ])  # Low variance = high kelly
        params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("A", "B", "C"),
            max_leverage=1.5,
        )
        kelly = MultiAssetKelly()
        result = kelly.optimize(params)

        assert result.leverage <= 1.5 + 1e-3

    def test_max_position_constraint(self) -> None:
        mu = np.array([0.20, 0.05])
        sigma = np.array([[0.02, 0], [0, 0.02]])
        params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("A", "B"),
            max_position=0.5,
            max_leverage=10.0,  # High leverage so position limit binds
        )
        kelly = MultiAssetKelly()
        result = kelly.optimize(params)

        for pos in result.optimal_positions.values():
            assert abs(pos) <= 0.5 + 1e-3

    def test_fractional_kelly_scales_positions(
        self, simple_params: MultiAssetKellyParams
    ) -> None:
        # Use moderate returns so constraints don't bind for both cases
        mu = np.array([0.05, 0.04, 0.06])
        sigma = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.03, 0.01],
            [0.02, 0.01, 0.05],
        ])
        full_params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("A", "B", "C"),
            fractional_kelly=1.0,
            max_leverage=10.0,
            max_position=5.0,
        )
        half_params = MultiAssetKellyParams(
            expected_returns=mu,
            covariance_matrix=sigma,
            asset_names=("A", "B", "C"),
            fractional_kelly=0.5,
            max_leverage=10.0,
            max_position=5.0,
        )

        kelly = MultiAssetKelly()
        full_result = kelly.optimize(full_params)
        half_result = kelly.optimize(half_params)

        # Half Kelly should have lower leverage (unless both hit max constraint)
        assert half_result.leverage <= full_result.leverage + 1e-6

    def test_sharpe_ratio_calculation(
        self, simple_params: MultiAssetKellyParams
    ) -> None:
        kelly = MultiAssetKelly()
        result = kelly.optimize(simple_params)

        assert result.sharpe_ratio >= 0

    def test_growth_rate_positive(self, simple_params: MultiAssetKellyParams) -> None:
        kelly = MultiAssetKelly()
        result = kelly.optimize(simple_params)

        # With positive expected returns, growth rate should be positive
        assert result.growth_rate > 0

    def test_result_to_dict(self, simple_params: MultiAssetKellyParams) -> None:
        kelly = MultiAssetKelly()
        result = kelly.optimize(simple_params)
        d = result.to_dict()

        assert "optimal_positions" in d
        assert "expected_return" in d
        assert "portfolio_variance" in d
        assert "sharpe_ratio" in d

    def test_compute_from_historical(self) -> None:
        # Generate synthetic returns
        np.random.seed(42)
        returns = np.random.randn(100, 3) * 0.02 + np.array([0.001, 0.0008, 0.0012])

        kelly = MultiAssetKelly()
        result = kelly.compute_from_historical(
            returns=returns,
            asset_names=["A", "B", "C"],
            fractional_kelly=0.5,
        )

        assert len(result.optimal_positions) == 3

    def test_compute_from_historical_with_lookback(self) -> None:
        np.random.seed(42)
        returns = np.random.randn(200, 2) * 0.02

        kelly = MultiAssetKelly()
        result = kelly.compute_from_historical(
            returns=returns,
            asset_names=["A", "B"],
            lookback=50,  # Only use last 50 periods
        )

        assert len(result.optimal_positions) == 2


class TestKellyFromEdgeVariance:
    """Tests for kelly_from_edge_variance helper function."""

    def test_basic_calculation(self) -> None:
        # f* = edge / variance
        fraction = kelly_from_edge_variance(edge=0.01, variance=0.04)
        assert fraction == pytest.approx(0.125)  # 0.5 * 0.01/0.04 = 0.125

    def test_zero_variance_returns_zero(self) -> None:
        fraction = kelly_from_edge_variance(edge=0.01, variance=0)
        assert fraction == 0.0

    def test_negative_variance_returns_zero(self) -> None:
        fraction = kelly_from_edge_variance(edge=0.01, variance=-0.01)
        assert fraction == 0.0

    def test_fractional_kelly_applied(self) -> None:
        full = kelly_from_edge_variance(edge=0.02, variance=0.04, fractional_kelly=1.0)
        half = kelly_from_edge_variance(edge=0.02, variance=0.04, fractional_kelly=0.5)

        assert half == pytest.approx(full * 0.5)

    def test_max_fraction_respected(self) -> None:
        # High edge/low variance would give high Kelly
        fraction = kelly_from_edge_variance(
            edge=0.5,
            variance=0.01,
            max_fraction=0.25,
        )
        assert fraction == 0.25

    def test_negative_edge_returns_zero(self) -> None:
        fraction = kelly_from_edge_variance(edge=-0.01, variance=0.04)
        assert fraction == 0.0
