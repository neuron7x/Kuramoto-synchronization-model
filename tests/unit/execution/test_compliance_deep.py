# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.compliance — target uncovered lines."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from domain import Order
from execution.compliance import (
    ComplianceMonitor,
    ComplianceReport,
    ComplianceViolation,
    RiskCompliance,
    RiskConfig,
    RiskDecision,
)
from execution.metrics import RiskMetrics
from execution.normalization import SymbolNormalizer, SymbolSpecification

# ── ComplianceReport ────────────────────────────────────────────────


class TestComplianceReport:
    def test_is_clean_no_violations(self):
        r = ComplianceReport(
            symbol="BTC",
            requested_quantity=1.0,
            requested_price=100.0,
            normalized_quantity=1.0,
            normalized_price=100.0,
            violations=(),
            blocked=False,
        )
        assert r.is_clean() is True

    def test_is_clean_with_violations(self):
        r = ComplianceReport(
            symbol="BTC",
            requested_quantity=1.0,
            requested_price=100.0,
            normalized_quantity=1.0,
            normalized_price=100.0,
            violations=("too small",),
            blocked=True,
        )
        assert r.is_clean() is False

    def test_to_dict(self):
        r = ComplianceReport(
            symbol="BTC",
            requested_quantity=1.0,
            requested_price=None,
            normalized_quantity=1.0,
            normalized_price=None,
            violations=("oops",),
            blocked=False,
        )
        d = r.to_dict()
        assert d["symbol"] == "BTC"
        assert d["violations"] == ["oops"]
        assert d["requested_price"] is None


# ── ComplianceViolation ─────────────────────────────────────────────


class TestComplianceViolation:
    def test_has_report(self):
        report = ComplianceReport(
            symbol="X",
            requested_quantity=0.5,
            requested_price=10.0,
            normalized_quantity=0.5,
            normalized_price=10.0,
            violations=("bad",),
            blocked=True,
        )
        exc = ComplianceViolation("fail", report=report)
        assert exc.report is report


# ── ComplianceMonitor ───────────────────────────────────────────────


class TestComplianceMonitor:
    @pytest.fixture()
    def normalizer(self):
        specs = {
            "BTCUSDT": SymbolSpecification(
                symbol="BTCUSDT",
                min_qty=0.001,
                min_notional=10.0,
                step_size=0.001,
                tick_size=0.01,
            ),
        }
        return SymbolNormalizer(specifications=specs)

    def test_clean_check(self, normalizer):
        mon = ComplianceMonitor(normalizer, strict=True, auto_round=True)
        report = mon.check("BTCUSDT", 1.0, 50000.0)
        assert report.is_clean()

    def test_strict_raises_on_violation(self, normalizer):
        mon = ComplianceMonitor(normalizer, strict=True, auto_round=True)
        with pytest.raises(ComplianceViolation):
            mon.check("BTCUSDT", 0.0001, 1.0)  # below min_notional

    def test_non_strict_returns_report(self, normalizer):
        mon = ComplianceMonitor(normalizer, strict=False, auto_round=True)
        report = mon.check("BTCUSDT", 0.0001, 1.0)
        assert not report.is_clean()
        assert report.blocked is False

    def test_no_auto_round(self, normalizer):
        mon = ComplianceMonitor(normalizer, strict=False, auto_round=False)
        report = mon.check("BTCUSDT", 1.0, 50000.0)
        assert report.normalized_quantity == 1.0

    def test_price_none(self, normalizer):
        mon = ComplianceMonitor(normalizer, strict=False, auto_round=True)
        report = mon.check("BTCUSDT", 1.0, None)
        assert report.normalized_price is None


# ── RiskDecision ────────────────────────────────────────────────────


class TestRiskDecision:
    def test_to_dict(self):
        rd = RiskDecision(
            allowed=True,
            reasons=(),
            breached_limits={},
            next_reset_at=None,
        )
        d = rd.to_dict()
        assert d["allowed"] is True
        assert d["next_reset_at"] is None

    def test_to_dict_with_reset(self):
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        rd = RiskDecision(
            allowed=False,
            reasons=("kill",),
            breached_limits={"kill": 1.0},
            next_reset_at=ts,
        )
        d = rd.to_dict()
        assert "2025" in d["next_reset_at"]


# ── RiskConfig ──────────────────────────────────────────────────────


class TestRiskConfig:
    def test_defaults(self):
        c = RiskConfig()
        assert c.kill_switch is False
        assert c.per_symbol_position_cap_overrides == {}

    def test_overrides_none_init(self):
        c = RiskConfig(per_symbol_position_cap_overrides=None)
        assert c.per_symbol_position_cap_overrides == {}


# ── RiskCompliance ──────────────────────────────────────────────────


def _make_order(symbol="BTC", side="buy", quantity=1.0, price=100.0):
    return Order(symbol=symbol, side=side, quantity=quantity, price=price)


def _make_portfolio(positions=None, gross_exposure=0.0, equity=10000.0, peak_equity=10000.0):
    return {
        "positions": positions or {},
        "gross_exposure": gross_exposure,
        "equity": equity,
        "peak_equity": peak_equity,
    }


class TestRiskCompliance:
    @pytest.fixture()
    def mock_metrics(self):
        m = MagicMock(spec=RiskMetrics)
        m.enabled = True
        return m

    def test_kill_switch_blocks(self, mock_metrics):
        cfg = RiskConfig(kill_switch=True)
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "Kill switch" in decision.reasons[0]

    def test_set_kill_switch(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        rc.set_kill_switch(True)
        state = rc.get_state()
        assert state["kill_switch"] is True

    def test_allowed_order(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is True

    def test_max_notional_breach(self, mock_metrics):
        cfg = RiskConfig(max_notional_per_order=50)
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(quantity=1.0, price=100.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "max_notional_per_order" in decision.breached_limits

    def test_position_cap_units(self, mock_metrics):
        cfg = RiskConfig(
            per_symbol_position_cap_type="units",
            per_symbol_position_cap_default=0.5,
        )
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(quantity=1.0, price=100.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "per_symbol_position_cap" in decision.breached_limits

    def test_position_cap_notional(self, mock_metrics):
        cfg = RiskConfig(
            per_symbol_position_cap_type="notional",
            per_symbol_position_cap_default=50,
        )
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(quantity=1.0, price=100.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "per_symbol_position_cap_notional" in decision.breached_limits

    def test_position_cap_override(self, mock_metrics):
        cfg = RiskConfig(
            per_symbol_position_cap_type="units",
            per_symbol_position_cap_default=100,
            per_symbol_position_cap_overrides={"BTC": 0.5},
        )
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(quantity=1.0, price=100.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False

    def test_gross_exposure_breach(self, mock_metrics):
        cfg = RiskConfig(max_gross_exposure=50)
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(quantity=1.0, price=100.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "max_gross_exposure" in decision.breached_limits

    def test_drawdown_percent_breach(self, mock_metrics):
        cfg = RiskConfig(
            daily_max_drawdown_mode="percent",
            daily_max_drawdown_threshold=0.05,
        )
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        portfolio = _make_portfolio(equity=9000, peak_equity=10000)
        decision = rc.check_order(order, {"price": 100}, portfolio)
        assert decision.allowed is False
        assert "daily_max_drawdown" in decision.breached_limits

    def test_drawdown_notional_breach(self, mock_metrics):
        cfg = RiskConfig(
            daily_max_drawdown_mode="notional",
            daily_max_drawdown_threshold=100,
        )
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        portfolio = _make_portfolio(equity=9000, peak_equity=10000)
        decision = rc.check_order(order, {"price": 100}, portfolio)
        assert decision.allowed is False
        assert "daily_max_drawdown_notional" in decision.breached_limits

    def test_max_open_orders_breach(self, mock_metrics):
        cfg = RiskConfig(max_open_orders_per_account=2)
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        rc.register_order_open()
        rc.register_order_open()
        order = _make_order()
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is False
        assert "max_open_orders" in decision.breached_limits

    def test_register_order_open_close(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        rc.register_order_open()
        rc.register_order_open()
        rc.register_order_close()
        assert rc.get_state()["open_orders_count"] == 1

    def test_register_order_close_at_zero(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        rc.register_order_close()  # should not go negative
        assert rc.get_state()["open_orders_count"] == 0

    def test_update_config(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        updated = rc.update_config(max_notional_per_order=999)
        assert updated.max_notional_per_order == 999

    def test_update_config_empty(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        same = rc.update_config()
        assert same is cfg

    def test_update_config_unknown_key(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        with pytest.raises(ValueError, match="Unknown"):
            rc.update_config(bogus_field=42)

    def test_get_state(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        state = rc.get_state()
        assert "kill_switch" in state
        assert "timestamp" in state

    def test_normalise_rejection_reason(self):
        assert RiskCompliance._normalise_rejection_reason("") == "unspecified"
        # The method replaces non-alnum with _, lowercases, strips _, collapses __
        result = RiskCompliance._normalise_rejection_reason("Test  Reason!")
        assert "__" not in result
        assert result == "test_reason"
        result2 = RiskCompliance._normalise_rejection_reason("a  b")
        assert "__" not in result2

    def test_sell_side_position_delta(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order(side="sell", quantity=1.0)
        decision = rc.check_order(order, {"price": 100}, _make_portfolio())
        assert decision.allowed is True

    def test_price_none_fallback(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = Order(symbol="BTC", side="buy", quantity=1.0, price=None, order_type="market")
        decision = rc.check_order(order, {}, _make_portfolio())
        assert decision.allowed is True

    def test_positions_non_dict(self, mock_metrics):
        cfg = RiskConfig()
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        portfolio = {
            "positions": "not_a_dict",
            "gross_exposure": 0,
            "equity": 10000,
            "peak_equity": 10000,
        }
        decision = rc.check_order(order, {"price": 100}, portfolio)
        assert isinstance(decision, RiskDecision)

    def test_daily_reset_occurs(self, mock_metrics):
        cfg = RiskConfig(daily_max_drawdown_mode="percent", daily_max_drawdown_threshold=0.5)
        rc = RiskCompliance(cfg, metrics=mock_metrics)
        order = _make_order()
        # First call sets daily_reset_time
        rc.check_order(order, {"price": 100}, _make_portfolio())
        # Second call checks should_reset_daily
        rc.check_order(order, {"price": 100}, _make_portfolio())
