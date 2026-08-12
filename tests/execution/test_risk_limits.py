# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.risk.core — RiskLimits and exception classes."""

from __future__ import annotations

import pytest

from execution.risk.core import (
    DataQualityError,
    LimitViolation,
    OrderRateExceeded,
    RiskError,
    RiskLimits,
)


class TestRiskExceptions:
    def test_risk_error_hierarchy(self):
        assert issubclass(RiskError, RuntimeError)

    def test_data_quality_error(self):
        err = DataQualityError("corrupt state")
        assert isinstance(err, RiskError)

    def test_limit_violation(self):
        err = LimitViolation("max notional exceeded")
        assert isinstance(err, RiskError)

    def test_order_rate_exceeded(self):
        err = OrderRateExceeded("throttled")
        assert isinstance(err, RiskError)


class TestRiskLimits:
    def test_defaults(self):
        rl = RiskLimits()
        assert rl.max_notional == float("inf")
        assert rl.max_position == float("inf")
        assert rl.max_orders_per_interval == 60
        assert rl.interval_seconds == 1.0
        assert rl.kill_switch_limit_multiplier == 1.5
        assert rl.kill_switch_violation_threshold == 3
        assert rl.kill_switch_rate_limit_threshold == 3
        assert rl.max_relative_drawdown is None

    def test_negative_orders_clamped(self):
        rl = RiskLimits(max_orders_per_interval=-5)
        assert rl.max_orders_per_interval == 0

    def test_negative_interval_clamped(self):
        rl = RiskLimits(interval_seconds=-1.0)
        assert rl.interval_seconds == 0.0

    def test_low_multiplier_clamped(self):
        rl = RiskLimits(kill_switch_limit_multiplier=0.5)
        assert rl.kill_switch_limit_multiplier == 1.0

    def test_low_violation_threshold_clamped(self):
        rl = RiskLimits(kill_switch_violation_threshold=0)
        assert rl.kill_switch_violation_threshold == 1

    def test_low_rate_threshold_clamped(self):
        rl = RiskLimits(kill_switch_rate_limit_threshold=-1)
        assert rl.kill_switch_rate_limit_threshold == 1

    def test_drawdown_as_ratio(self):
        rl = RiskLimits(max_relative_drawdown=0.1)
        assert rl.max_relative_drawdown == pytest.approx(0.1)

    def test_drawdown_as_percentage(self):
        rl = RiskLimits(max_relative_drawdown=10.0)
        assert rl.max_relative_drawdown == pytest.approx(0.1)

    def test_drawdown_100_percent(self):
        rl = RiskLimits(max_relative_drawdown=100.0)
        assert rl.max_relative_drawdown == pytest.approx(1.0)

    def test_drawdown_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            RiskLimits(max_relative_drawdown=0.0)

    def test_drawdown_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            RiskLimits(max_relative_drawdown=-5.0)

    def test_drawdown_over_100_raises(self):
        with pytest.raises(ValueError, match="100"):
            RiskLimits(max_relative_drawdown=150.0)

    def test_custom_values(self):
        rl = RiskLimits(
            max_notional=1e6,
            max_position=100.0,
            max_orders_per_interval=10,
            interval_seconds=60.0,
        )
        assert rl.max_notional == 1e6
        assert rl.max_position == 100.0
        assert rl.max_orders_per_interval == 10
        assert rl.interval_seconds == 60.0

    @pytest.mark.parametrize("dd", [0.01, 0.05, 0.1, 0.5, 0.99])
    def test_valid_ratio_drawdowns(self, dd):
        rl = RiskLimits(max_relative_drawdown=dd)
        assert rl.max_relative_drawdown == pytest.approx(dd)

    @pytest.mark.parametrize("dd", [1.0, 5.0, 10.0, 50.0, 100.0])
    def test_percentage_drawdowns_converted(self, dd):
        rl = RiskLimits(max_relative_drawdown=dd)
        assert rl.max_relative_drawdown == pytest.approx(dd / 100.0)
