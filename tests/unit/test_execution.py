# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from domain import Order, OrderType
from execution.audit import ExecutionAuditLogger
from execution.order import position_sizing
from execution.risk import (
    IdempotentRetryExecutor,
    LimitViolation,
    OrderRateExceeded,
    RiskError,
    RiskLimits,
    RiskManager,
    portfolio_heat,
)


def test_order_defaults_to_market_type() -> None:
    order = Order(symbol="BTCUSD", side="buy", quantity=1.0)
    assert order.order_type == OrderType.MARKET
    assert order.price is None


def test_position_sizing_never_exceeds_balance() -> None:
    balance = 1000.0
    risk = 0.1
    price = 50.0
    size = position_sizing(balance, risk, price)
    assert size <= balance / price
    assert size >= 0.0


def test_portfolio_heat_sums_absolute_exposure() -> None:
    positions = [
        {"qty": 2.0, "price": 100.0},
        {"qty": -1.0, "price": 50.0},
    ]
    heat = portfolio_heat(positions)
    expected = abs(2.0 * 100.0) + abs(-1.0 * 50.0)
    assert heat == pytest.approx(expected, rel=1e-12)


class _TimeStub:
    def __init__(self) -> None:
        self._now = 0.0

    def advance(self, delta: float) -> None:
        self._now += delta

    def __call__(self) -> float:
        return self._now


def test_risk_manager_enforces_position_and_notional_caps() -> None:
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=100.0,
        max_position=5.0,
        max_orders_per_interval=5,
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    manager.validate_order("BTC", "buy", qty=2.0, price=20.0)
    manager.register_fill("BTC", "buy", qty=2.0, price=20.0)
    assert manager.current_position("BTC") == pytest.approx(2.0)

    with pytest.raises(LimitViolation):
        manager.validate_order("BTC", "buy", qty=5.0, price=25.0)

    with pytest.raises(LimitViolation):
        manager.validate_order("BTC", "sell", qty=8.0, price=40.0)


def test_risk_manager_rate_limiter_blocks_excess_orders() -> None:
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_orders_per_interval=2,
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)
    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)
    with pytest.raises(OrderRateExceeded):
        manager.validate_order("ETH", "buy", qty=1.0, price=10.0)

    clock.advance(1.1)
    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)


def test_risk_manager_does_not_accumulate_submissions_when_throttling_disabled() -> (
    None
):
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=1_000_000.0,
        max_position=1_000_000.0,
        max_orders_per_interval=0,
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    for _ in range(256):
        manager.validate_order("BTC", "buy", qty=1.0, price=10.0)
        clock.advance(0.1)

    assert len(manager._submissions) == 0


def test_kill_switch_blocks_all_orders() -> None:
    manager = RiskManager(RiskLimits(max_notional=100.0, max_position=10.0))
    manager.kill_switch.trigger("test")
    with pytest.raises(RiskError):
        manager.validate_order("BTC", "buy", qty=1.0, price=10.0)


def test_risk_manager_trips_kill_switch_on_severe_violation(tmp_path) -> None:
    clock = _TimeStub()
    audit_path = tmp_path / "audit.jsonl"
    audit = ExecutionAuditLogger(audit_path)
    limits = RiskLimits(
        max_notional=100.0,
        max_position=5.0,
        kill_switch_limit_multiplier=1.1,
    )
    manager = RiskManager(limits, time_source=clock, audit_logger=audit)

    with pytest.raises(LimitViolation):
        manager.validate_order("BTC", "buy", qty=6.0, price=10.0)

    assert manager.kill_switch.is_triggered()
    assert "Position cap exceeded" in manager.kill_switch.reason

    entries = [
        json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
    ]
    kill_events = [
        entry for entry in entries if entry.get("event") == "kill_switch_triggered"
    ]
    assert kill_events and kill_events[0]["violation_type"] == "position_limit"


def test_risk_manager_trips_kill_switch_after_repeated_throttling(tmp_path) -> None:
    clock = _TimeStub()
    audit_path = tmp_path / "rate_audit.jsonl"
    audit = ExecutionAuditLogger(audit_path)
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_orders_per_interval=1,
        interval_seconds=5.0,
        kill_switch_rate_limit_threshold=2,
    )
    manager = RiskManager(limits, time_source=clock, audit_logger=audit)

    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)
    with pytest.raises(OrderRateExceeded):
        manager.validate_order("ETH", "buy", qty=1.0, price=10.0)
    with pytest.raises(OrderRateExceeded):
        manager.validate_order("ETH", "buy", qty=1.0, price=10.0)

    assert manager.kill_switch.is_triggered()
    assert "Order throttle exceeded" in manager.kill_switch.reason


def test_risk_manager_normalises_symbol_aliases() -> None:
    manager = RiskManager(RiskLimits(max_notional=1_000.0, max_position=10.0))
    manager.validate_order("btc-usdt", "buy", qty=1.0, price=20.0)
    manager.register_fill("BTCUSDT", "buy", qty=1.0, price=20.0)
    assert manager.current_position("btc/usdt") == pytest.approx(1.0)
    assert manager.current_notional("BTC_USDT") == pytest.approx(20.0)


def test_risk_manager_blocks_when_gross_exposure_exceeds_limit() -> None:
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_gross_exposure=200.0,
    )
    manager = RiskManager(limits)
    manager.update_portfolio_equity(10_000.0)

    manager.validate_order("ETH", "buy", qty=1.0, price=50.0)
    manager.register_fill("ETH", "buy", qty=1.0, price=50.0)

    with pytest.raises(LimitViolation) as exc:
        manager.validate_order("ETH", "buy", qty=2.0, price=100.0)

    assert "gross exposure" in str(exc.value).lower()


def test_risk_manager_blocks_on_portfolio_heat_cap() -> None:
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_gross_exposure=10_000.0,
        max_portfolio_heat=120.0,
    )
    manager = RiskManager(limits)
    manager.update_portfolio_equity(5_000.0)

    manager.validate_order("SOL", "buy", qty=1.0, price=50.0)
    manager.register_fill("SOL", "buy", qty=1.0, price=50.0)

    with pytest.raises(LimitViolation) as exc:
        manager.validate_order("SOL", "buy", qty=1.0, price=100.0)

    assert "risk heat" in str(exc.value).lower()


def test_risk_manager_blocks_on_leverage_limit() -> None:
    limits = RiskLimits(
        max_notional=5_000.0,
        max_position=1_000.0,
        max_gross_exposure=10_000.0,
        max_leverage=2.0,
    )
    manager = RiskManager(limits)
    manager.update_portfolio_equity(100.0)

    manager.validate_order("BTC", "buy", qty=1.0, price=20.0)
    manager.register_fill("BTC", "buy", qty=1.0, price=20.0)

    with pytest.raises(LimitViolation) as exc:
        manager.validate_order("BTC", "buy", qty=2.0, price=150.0)

    assert "leverage" in str(exc.value).lower()


def test_risk_manager_blocks_when_daily_drawdown_exceeded() -> None:
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_daily_drawdown=0.1,
    )
    manager = RiskManager(limits)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    manager.update_portfolio_equity(1_000.0, timestamp=start)
    manager.update_portfolio_equity(850.0, timestamp=start + timedelta(hours=1))

    with pytest.raises(LimitViolation) as exc:
        manager.validate_order("ADA", "buy", qty=1.0, price=10.0)

    assert "drawdown" in str(exc.value).lower()


def test_idempotent_retry_executor_retries_and_caches() -> None:
    executor = IdempotentRetryExecutor()
    attempts: list[int] = []

    def flaky(attempt: int) -> str:
        attempts.append(attempt)
        if attempt < 2:
            raise RuntimeError("boom")
        return "ok"

    result = executor.run("order-1", flaky, retries=3, retry_exceptions=(RuntimeError,))
    assert result == "ok"
    assert attempts == [1, 2]
    # Second call should be cached and not invoke callable
    assert executor.run("order-1", flaky, retries=3) == "ok"
