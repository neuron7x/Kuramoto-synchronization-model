# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for portfolio rebalancing module."""

from __future__ import annotations

import numpy as np
import pytest

from analytics.math_trading.portfolio_rebalancing import (
    PortfolioRebalancer,
    RebalanceConstraints,
    RebalanceRequest,
    compute_minimum_variance_trades,
)


class TestRebalanceConstraints:
    """Tests for RebalanceConstraints validation."""

    def test_valid_constraints(self) -> None:
        constraints = RebalanceConstraints(
            tolerance=0.05,
            min_trade_size=0.001,
            max_turnover=0.5,
        )
        assert constraints.tolerance == 0.05

    def test_negative_tolerance_raises(self) -> None:
        with pytest.raises(ValueError, match="tolerance must be non-negative"):
            RebalanceConstraints(tolerance=-0.01)

    def test_negative_min_trade_raises(self) -> None:
        with pytest.raises(ValueError, match="min_trade_size must be non-negative"):
            RebalanceConstraints(min_trade_size=-0.001)

    def test_zero_turnover_raises(self) -> None:
        with pytest.raises(ValueError, match="max_turnover must be positive"):
            RebalanceConstraints(max_turnover=0)

    def test_invalid_cash_bounds_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid cash weight bounds"):
            RebalanceConstraints(cash_weight_min=0.5, cash_weight_max=0.3)


class TestRebalanceRequest:
    """Tests for RebalanceRequest validation."""

    def test_valid_request(self) -> None:
        request = RebalanceRequest(
            current_weights={"AAPL": 0.5, "GOOG": 0.5},
            target_weights={"AAPL": 0.6, "GOOG": 0.4},
        )
        assert request.portfolio_value == 1.0

    def test_empty_current_raises(self) -> None:
        with pytest.raises(ValueError, match="current_weights cannot be empty"):
            RebalanceRequest(
                current_weights={},
                target_weights={"AAPL": 1.0},
            )

    def test_empty_target_raises(self) -> None:
        with pytest.raises(ValueError, match="target_weights cannot be empty"):
            RebalanceRequest(
                current_weights={"AAPL": 1.0},
                target_weights={},
            )

    def test_negative_portfolio_value_raises(self) -> None:
        with pytest.raises(ValueError, match="portfolio_value must be positive"):
            RebalanceRequest(
                current_weights={"AAPL": 1.0},
                target_weights={"AAPL": 1.0},
                portfolio_value=-100,
            )


class TestPortfolioRebalancer:
    """Tests for PortfolioRebalancer."""

    @pytest.fixture
    def simple_request(self) -> RebalanceRequest:
        return RebalanceRequest(
            current_weights={"AAPL": 0.3, "GOOG": 0.3, "MSFT": 0.4},
            target_weights={"AAPL": 0.33, "GOOG": 0.33, "MSFT": 0.34},
            transaction_costs={"AAPL": 0.001, "GOOG": 0.001, "MSFT": 0.001},
            portfolio_value=100000,
        )

    def test_optimization_succeeds(self, simple_request: RebalanceRequest) -> None:
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(simple_request)

        assert result.optimization_success

    def test_final_weights_sum_to_one(self, simple_request: RebalanceRequest) -> None:
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(simple_request)

        total = sum(result.final_weights.values())
        assert total == pytest.approx(1.0, rel=1e-4)

    def test_trades_within_tolerance(self) -> None:
        constraints = RebalanceConstraints(tolerance=0.05)
        rebalancer = PortfolioRebalancer(constraints=constraints)

        request = RebalanceRequest(
            current_weights={"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25},
            target_weights={"A": 0.30, "B": 0.20, "C": 0.30, "D": 0.20},
        )
        result = rebalancer.optimize(request)

        for asset in ["A", "B", "C", "D"]:
            target = request.target_weights[asset]
            actual = result.final_weights[asset]
            assert abs(actual - target) <= constraints.tolerance + 1e-6

    def test_turnover_calculation(self, simple_request: RebalanceRequest) -> None:
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(simple_request)

        # Turnover should be reasonable for small rebalance
        assert result.total_turnover >= 0
        assert result.total_turnover <= 1.0

    def test_transaction_cost_calculation(self, simple_request: RebalanceRequest) -> None:
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(simple_request)

        # Transaction cost should be non-negative
        assert result.total_transaction_cost >= 0

        # Should match sum of order costs
        order_costs = sum(o.transaction_cost for o in result.orders)
        assert result.total_transaction_cost == pytest.approx(order_costs, rel=1e-6)

    def test_no_trade_when_at_target(self) -> None:
        request = RebalanceRequest(
            current_weights={"A": 0.5, "B": 0.5},
            target_weights={"A": 0.5, "B": 0.5},
        )
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(request)

        # No trades needed
        assert len(result.orders) == 0
        assert result.total_turnover < 0.001

    def test_long_only_constraint(self) -> None:
        constraints = RebalanceConstraints(long_only=True)
        rebalancer = PortfolioRebalancer(constraints=constraints)

        request = RebalanceRequest(
            current_weights={"A": 0.8, "B": 0.2},
            target_weights={"A": 0.0, "B": 1.0},
        )
        result = rebalancer.optimize(request)

        # All weights should be non-negative
        for weight in result.final_weights.values():
            assert weight >= -1e-9

    def test_min_trade_size_filter(self) -> None:
        constraints = RebalanceConstraints(min_trade_size=0.05)
        rebalancer = PortfolioRebalancer(constraints=constraints)

        request = RebalanceRequest(
            current_weights={"A": 0.50, "B": 0.50},
            target_weights={"A": 0.51, "B": 0.49},  # Very small rebalance
        )
        result = rebalancer.optimize(request)

        # Trades below min size should be filtered
        for order in result.orders:
            assert abs(order.trade_weight) >= constraints.min_trade_size

    def test_new_asset_in_target(self) -> None:
        """Test handling of assets that appear only in target."""
        request = RebalanceRequest(
            current_weights={"A": 0.5, "B": 0.5},
            target_weights={"A": 0.33, "B": 0.33, "C": 0.34},
        )
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(request)

        assert "C" in result.final_weights
        assert result.optimization_success

    def test_asset_removed_from_target(self) -> None:
        """Test handling of assets that should be sold completely."""
        constraints = RebalanceConstraints(tolerance=0.01)
        rebalancer = PortfolioRebalancer(constraints=constraints)

        request = RebalanceRequest(
            current_weights={"A": 0.33, "B": 0.33, "C": 0.34},
            target_weights={"A": 0.5, "B": 0.5},  # C not in target
        )
        result = rebalancer.optimize(request)

        # C should be close to 0
        assert result.final_weights.get("C", 0) < 0.02

    def test_result_to_dict(self, simple_request: RebalanceRequest) -> None:
        rebalancer = PortfolioRebalancer()
        result = rebalancer.optimize(simple_request)
        d = result.to_dict()

        assert "orders" in d
        assert "total_turnover" in d
        assert "total_transaction_cost" in d
        assert "final_weights" in d

    def test_tracking_penalty_effect(self) -> None:
        """Higher tracking penalty should result in weights closer to target."""
        request = RebalanceRequest(
            current_weights={"A": 0.4, "B": 0.6},
            target_weights={"A": 0.5, "B": 0.5},
            transaction_costs={"A": 0.01, "B": 0.01},  # High costs
        )

        low_penalty = PortfolioRebalancer(tracking_penalty=0.1)
        high_penalty = PortfolioRebalancer(tracking_penalty=10.0)

        low_result = low_penalty.optimize(request)
        high_result = high_penalty.optimize(request)

        # High penalty should track target more closely
        low_error = sum(
            (low_result.final_weights[a] - request.target_weights[a]) ** 2 for a in ["A", "B"]
        )
        high_error = sum(
            (high_result.final_weights[a] - request.target_weights[a]) ** 2 for a in ["A", "B"]
        )

        assert high_error <= low_error


class TestMinimumVarianceTrades:
    """Tests for compute_minimum_variance_trades function."""

    @pytest.fixture
    def simple_setup(self) -> tuple:
        asset_names = ["A", "B", "C"]
        cov = np.array(
            [
                [0.04, 0.01, 0.005],
                [0.01, 0.03, 0.01],
                [0.005, 0.01, 0.02],
            ]
        )
        current = {"A": 0.3, "B": 0.4, "C": 0.3}
        target = {"A": 0.4, "B": 0.3, "C": 0.3}
        return current, target, cov, asset_names

    def test_basic_computation(self, simple_setup: tuple) -> None:
        current, target, cov, names = simple_setup
        trades = compute_minimum_variance_trades(
            current_weights=current,
            target_weights=target,
            covariance_matrix=cov,
            asset_names=names,
            risk_budget=0.1,
        )

        assert set(trades.keys()) == set(names)

    def test_full_rebalance_within_budget(self, simple_setup: tuple) -> None:
        current, target, cov, names = simple_setup
        trades = compute_minimum_variance_trades(
            current_weights=current,
            target_weights=target,
            covariance_matrix=cov,
            asset_names=names,
            risk_budget=1.0,  # Very large budget
        )

        # Should match full delta
        for name in names:
            expected = target[name] - current[name]
            assert trades[name] == pytest.approx(expected, rel=1e-6)

    def test_scaled_rebalance_with_small_budget(self, simple_setup: tuple) -> None:
        current, target, cov, names = simple_setup
        trades = compute_minimum_variance_trades(
            current_weights=current,
            target_weights=target,
            covariance_matrix=cov,
            asset_names=names,
            risk_budget=0.0001,  # Very small budget
        )

        # Trades should be scaled down
        full_delta = sum(abs(target[n] - current[n]) for n in names)
        actual_delta = sum(abs(trades[n]) for n in names)
        # Allow for numerical precision
        assert actual_delta <= full_delta + 1e-9

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="covariance_matrix dimension mismatch"):
            compute_minimum_variance_trades(
                current_weights={"A": 0.5, "B": 0.5},
                target_weights={"A": 0.6, "B": 0.4},
                covariance_matrix=np.eye(3),  # Wrong size
                asset_names=["A", "B"],
            )
