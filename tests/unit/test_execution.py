# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for execution and risk management components.

This module validates the core execution infrastructure including:
- Order model and validation
- Position sizing calculations
- Risk limit enforcement (position, notional, rate)
- Kill switch emergency stop mechanism
- Audit logging for compliance
- Idempotent retry logic

The risk management system is critical for preventing trading losses
and ensuring regulatory compliance. These tests verify that all risk
controls work correctly under normal and edge case conditions.

Coverage: execution/risk.py, execution/order.py, execution/audit.py
"""
from __future__ import annotations

import json

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
    """Test that Order objects default to MARKET type when not specified.

    Market orders execute immediately at current market price, which
    is the default behavior when no order type is specified.

    Validates:
    - Default order type is MARKET
    - Price field is None for market orders
    """
    order = Order(symbol="BTCUSD", side="buy", quantity=1.0)
    assert order.order_type == OrderType.MARKET, "Should default to MARKET type"
    assert order.price is None, "Market orders should not have a price"


def test_position_sizing_never_exceeds_balance() -> None:
    """Test that position sizing respects maximum balance constraints.

    Position sizing must ensure that the total cost of a position
    never exceeds available capital, even with maximum risk allocation.

    Validates:
    - Calculated size doesn't exceed balance/price
    - Result is always non-negative
    - Works with various risk parameters
    """
    balance = 1000.0
    risk = 0.1
    price = 50.0
    size = position_sizing(balance, risk, price)
    assert size <= balance / price, f"Size {size} exceeds max {balance/price}"
    assert size >= 0.0, "Size must be non-negative"


def test_portfolio_heat_sums_absolute_exposure() -> None:
    """Test that portfolio heat correctly calculates total exposure.

    Portfolio heat measures total capital at risk across all positions,
    considering both long and short positions as positive exposure.

    Validates:
    - Long and short positions both contribute to heat
    - Calculation uses absolute values
    - Result matches manual calculation
    """
    positions = [
        {"qty": 2.0, "price": 100.0},
        {"qty": -1.0, "price": 50.0},
    ]
    heat = portfolio_heat(positions)
    expected = abs(2.0 * 100.0) + abs(-1.0 * 50.0)
    assert heat == pytest.approx(
        expected, rel=1e-12
    ), f"Heat calculation incorrect: expected {expected}, got {heat}"


class _TimeStub:
    """Controllable time source for deterministic time-dependent testing.

    Allows tests to control the passage of time without actual delays,
    making tests faster and deterministic.
    """

    def __init__(self) -> None:
        self._now = 0.0

    def advance(self, delta: float) -> None:
        """Advance the clock by delta seconds."""
        self._now += delta

    def __call__(self) -> float:
        """Return current time in seconds since epoch."""
        return self._now


def test_risk_manager_enforces_position_and_notional_caps() -> None:
    """Test that risk manager prevents positions exceeding configured limits.

    Risk manager must enforce both position size (quantity) and notional
    value (quantity * price) limits to prevent over-exposure.

    Validates:
    - Position limits are enforced on new orders
    - Notional limits prevent excessive capital allocation
    - Current position tracking is accurate
    - Both long and short limit violations are caught
    """
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=100.0,
        max_position=5.0,
        max_orders_per_interval=5,
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    # Successfully place and fill an order within limits
    manager.validate_order("BTC", "buy", qty=2.0, price=20.0)
    manager.register_fill("BTC", "buy", qty=2.0, price=20.0)
    assert manager.current_position("BTC") == pytest.approx(
        2.0
    ), "Position should be tracked correctly"

    # Attempt to exceed position limit
    with pytest.raises(LimitViolation, match="[Pp]osition"):
        manager.validate_order("BTC", "buy", qty=5.0, price=25.0)

    # Attempt to exceed notional limit on opposite side
    with pytest.raises(LimitViolation, match="[Nn]otional|[Pp]osition"):
        manager.validate_order("BTC", "sell", qty=8.0, price=40.0)


def test_risk_manager_rate_limiter_blocks_excess_orders() -> None:
    """Test that order rate limiting prevents excessive trading activity.

    Rate limiting is critical for:
    - Preventing accidental order floods from bugs
    - Complying with exchange rate limits
    - Reducing transaction costs

    Validates:
    - Rate limiter counts orders within time window
    - Excess orders are rejected with OrderRateExceeded
    - Rate limit resets after time interval passes
    """
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=1_000.0,
        max_position=100.0,
        max_orders_per_interval=2,
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    # First two orders should succeed
    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)
    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)

    # Third order exceeds rate limit
    with pytest.raises(OrderRateExceeded, match="[Rr]ate|[Ee]xceeded"):
        manager.validate_order("ETH", "buy", qty=1.0, price=10.0)

    # After time window, rate limit resets
    clock.advance(1.1)
    manager.validate_order("ETH", "buy", qty=1.0, price=10.0)


def test_risk_manager_does_not_accumulate_submissions_when_throttling_disabled() -> (
    None
):
    """Test that disabling throttling prevents memory accumulation.

    When rate limiting is disabled (max_orders_per_interval=0),
    the risk manager should not accumulate submission timestamps
    to avoid memory leaks.

    Validates:
    - Disabled throttling doesn't track submissions
    - Memory doesn't grow with order count
    - All orders are accepted regardless of frequency
    """
    clock = _TimeStub()
    limits = RiskLimits(
        max_notional=1_000_000.0,
        max_position=1_000_000.0,
        max_orders_per_interval=0,  # Throttling disabled
        interval_seconds=1.0,
    )
    manager = RiskManager(limits, time_source=clock)

    # Submit many orders without rate limiting
    for _ in range(256):
        manager.validate_order("BTC", "buy", qty=1.0, price=10.0)
        clock.advance(0.1)

    # Verify submissions list doesn't accumulate
    assert (
        len(manager._submissions) == 0
    ), "Submissions should not accumulate when throttling is disabled"


def test_kill_switch_blocks_all_orders() -> None:
    """Test that triggered kill switch prevents all trading activity.

    The kill switch is an emergency stop mechanism that immediately
    halts all trading when triggered by severe violations or manual intervention.

    Validates:
    - Kill switch can be manually triggered
    - All orders are rejected when kill switch is active
    - Rejection raises RiskError with appropriate message
    """
    manager = RiskManager(RiskLimits(max_notional=100.0, max_position=10.0))
    manager.kill_switch.trigger("test")

    with pytest.raises(RiskError, match="[Kk]ill.*[Ss]witch"):
        manager.validate_order("BTC", "buy", qty=1.0, price=10.0)


def test_risk_manager_trips_kill_switch_on_severe_violation(tmp_path) -> None:
    """Test that severe risk violations automatically trigger kill switch.

    Critical risk violations (exceeding limits by configured threshold)
    should automatically trigger the kill switch to prevent cascading failures.
    This behavior is essential for preventing large losses from bugs or attacks.

    Validates:
    - Severe violations trigger automatic kill switch
    - Kill switch reason is recorded
    - Audit log captures kill switch event
    - Event includes violation type and details
    """
    clock = _TimeStub()
    audit_path = tmp_path / "audit.jsonl"
    audit = ExecutionAuditLogger(audit_path)
    limits = RiskLimits(
        max_notional=100.0,
        max_position=5.0,
        kill_switch_limit_multiplier=1.1,  # Trigger at 10% over limit
    )
    manager = RiskManager(limits, time_source=clock, audit_logger=audit)

    # Attempt severe position limit violation
    with pytest.raises(LimitViolation):
        manager.validate_order("BTC", "buy", qty=6.0, price=10.0)

    # Verify kill switch was triggered
    assert manager.kill_switch.is_triggered(), "Kill switch should be triggered"
    assert (
        "Position cap exceeded" in manager.kill_switch.reason
    ), "Reason should mention position cap"

    # Verify audit log captured the event
    entries = [
        json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
    ]
    kill_events = [
        entry for entry in entries if entry.get("event") == "kill_switch_triggered"
    ]
    assert kill_events, "Kill switch event should be in audit log"
    assert (
        kill_events[0]["violation_type"] == "position_limit"
    ), "Event should specify violation type"


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


def test_risk_limits_normalises_drawdown_percentage() -> None:
    limits = RiskLimits(max_relative_drawdown=5)
    assert limits.max_relative_drawdown == pytest.approx(0.05)


def test_risk_manager_drawdown_kill_switch(tmp_path) -> None:
    audit_path = tmp_path / "drawdown_audit.jsonl"
    audit = ExecutionAuditLogger(audit_path)
    limits = RiskLimits(
        max_notional=1_000_000.0,
        max_position=1_000.0,
        max_relative_drawdown=0.05,
    )
    manager = RiskManager(limits, audit_logger=audit)

    manager.update_portfolio_equity(100_000.0, realized_pnl=0.0, unrealized_pnl=0.0)
    assert manager.current_drawdown == pytest.approx(0.0)
    assert not manager.kill_switch.is_triggered()

    manager.update_portfolio_equity(97_000.0)
    assert manager.current_drawdown == pytest.approx(0.03)
    assert not manager.kill_switch.is_triggered()

    manager.update_portfolio_equity(94_000.0, realized_pnl=-6_000.0)
    assert manager.kill_switch.is_triggered()
    assert manager.paper_trading_active is True
    reason = manager.kill_switch.reason.lower()
    assert "drawdown" in reason
    assert "paper" in reason

    entries = [
        json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
    ]
    breach = [
        entry for entry in entries if entry.get("event") == "portfolio_drawdown_breach"
    ]
    assert breach
    last = breach[-1]
    assert last["drawdown"] >= limits.max_relative_drawdown
    assert last["equity"] == pytest.approx(94_000.0)
    assert last["peak_equity"] == pytest.approx(100_000.0)


def test_update_portfolio_equity_rejects_invalid_values() -> None:
    manager = RiskManager(RiskLimits(max_relative_drawdown=0.1))

    with pytest.raises(ValueError):
        manager.update_portfolio_equity(float("nan"))

    with pytest.raises(ValueError):
        manager.update_portfolio_equity(-1.0)


def test_risk_manager_normalises_symbol_aliases() -> None:
    manager = RiskManager(RiskLimits(max_notional=1_000.0, max_position=10.0))
    manager.validate_order("btc-usdt", "buy", qty=1.0, price=20.0)
    manager.register_fill("BTCUSDT", "buy", qty=1.0, price=20.0)
    assert manager.current_position("btc/usdt") == pytest.approx(1.0)
    assert manager.current_notional("BTC_USDT") == pytest.approx(20.0)


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
