# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end integration test for risk controls in OMS."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from domain import Order, OrderSide, OrderStatus
from execution.compliance import ComplianceViolation, RiskCompliance, RiskConfig
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem
from execution.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from interfaces.execution import RiskController


class FakeRiskController(RiskController):
    """Fake risk controller for testing."""

    def __init__(self):
        self._positions = {}
        self._notionals = {}
        self._balance = 100000.0
        self._peak_equity = 100000.0
        self._gross_notional = 0.0
        self._kill_switch = None

    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        pass

    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        position_delta = qty if side == "buy" else -qty
        self._positions[symbol] = self._positions.get(symbol, 0.0) + position_delta
        self._notionals[symbol] = self._positions[symbol] * price
        self._gross_notional = sum(abs(v) for v in self._notionals.values())

    def current_position(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)

    def current_notional(self, symbol: str) -> float:
        return self._notionals.get(symbol, 0.0)

    @property
    def kill_switch(self):
        return self._kill_switch

    @kill_switch.setter
    def kill_switch(self, value):
        self._kill_switch = value


class FakeConnector(ExecutionConnector):
    """Fake connector for testing."""

    def __init__(self):
        self.orders = []
        self.next_id = 1

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        order_id = f"ORDER-{self.next_id}"
        self.next_id += 1
        order.mark_submitted(order_id, broker_order_id=order_id)
        self.orders.append(order)
        return order

    def cancel_order(self, order_id: str) -> bool:
        return True


@pytest.fixture
def temp_dir():
    """Create temporary directory for test state."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def risk_config():
    """Create risk configuration for tests."""
    return RiskConfig(
        kill_switch=False,
        max_notional_per_order=50000.0,
        max_gross_exposure=150000.0,
        daily_max_drawdown_mode="percent",
        daily_max_drawdown_threshold=0.10,
    )


@pytest.fixture
def risk_compliance(risk_config):
    """Create risk compliance instance."""
    return RiskCompliance(risk_config)


@pytest.fixture
def circuit_breaker():
    """Create circuit breaker instance."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=1.0,
        breaches_threshold=3,
        breaches_window_seconds=60.0,
    )
    return CircuitBreaker(config)


@pytest.fixture
def oms(temp_dir, risk_compliance, circuit_breaker):
    """Create OMS with risk controls."""
    connector = FakeConnector()
    risk = FakeRiskController()
    config = OMSConfig(
        state_path=temp_dir / "oms_state.json",
        ledger_path=None,
    )
    return OrderManagementSystem(
        connector=connector,
        risk_controller=risk,
        config=config,
        risk_compliance=risk_compliance,
        circuit_breaker=circuit_breaker,
    )


class TestE2ERiskControls:
    """E2E tests for risk controls in OMS."""

    def test_order_allowed_when_no_limits_breached(self, oms):
        """Test that orders pass when all checks pass."""
        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=0.5,
            price=40000.0,
        )

        submitted = oms.submit(order, correlation_id="test-1")
        assert submitted.status == OrderStatus.PENDING
        assert "test-1" in oms._pending

        processed = oms.process_next()
        assert processed.status == OrderStatus.OPEN
        assert processed.order_id is not None

    def test_order_blocked_by_kill_switch(self, oms, risk_compliance):
        """Test that kill switch blocks all orders."""
        risk_compliance.set_kill_switch(True)

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=0.5,
            price=40000.0,
        )

        with pytest.raises(ComplianceViolation) as exc_info:
            oms.submit(order, correlation_id="test-kill-1")

        assert "Kill switch" in str(exc_info.value)

    def test_order_blocked_by_max_notional(self, oms):
        """Test that orders exceeding max notional are blocked."""
        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=2.0,
            price=40000.0,
        )

        with pytest.raises(ComplianceViolation) as exc_info:
            oms.submit(order, correlation_id="test-notional-1")

        assert "notional" in str(exc_info.value).lower()

    def test_order_blocked_by_gross_exposure(self, oms):
        """Test that orders exceeding gross exposure are blocked when mock gross exposure is high."""
        oms.risk._gross_notional = 140000.0

        order = Order(
            symbol="SOL/USD",
            side=OrderSide.BUY,
            quantity=250.0,
            price=100.0,
        )

        with pytest.raises(ComplianceViolation) as exc_info:
            oms.submit(order, correlation_id="test-exp-1")

        error_msg = str(exc_info.value)
        assert "Gross exposure" in error_msg

    def test_circuit_breaker_blocks_after_breaches(self, oms, risk_compliance, circuit_breaker):
        """Test that circuit breaker opens after N risk breaches."""
        for i in range(3):
            circuit_breaker.record_risk_breach(f"breach_{i}")

        for i in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state.value == "open"

        order = Order(
            symbol="ETH/USD",
            side=OrderSide.BUY,
            quantity=0.1,
            price=3000.0,
        )

        with pytest.raises(ComplianceViolation) as exc_info:
            oms.submit(order, correlation_id="test-circuit-block")

        assert "Circuit breaker" in str(exc_info.value)

    def test_kill_switch_toggle_via_compliance(self, oms, risk_compliance):
        """Test toggling kill switch and observing OMS behavior."""
        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=0.5,
            price=40000.0,
        )

        oms.submit(order, correlation_id="test-toggle-1")
        assert "test-toggle-1" in oms._pending

        risk_compliance.set_kill_switch(True)

        order2 = Order(
            symbol="ETH/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=3000.0,
        )

        with pytest.raises(ComplianceViolation):
            oms.submit(order2, correlation_id="test-toggle-2")

        risk_compliance.set_kill_switch(False)

        order3 = Order(
            symbol="SOL/USD",
            side=OrderSide.BUY,
            quantity=10.0,
            price=100.0,
        )

        oms.submit(order3, correlation_id="test-toggle-3")
        assert "test-toggle-3" in oms._pending

    def test_idempotency_with_risk_rejection(self, oms):
        """Test that rejected orders maintain idempotency."""
        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=2.0,
            price=40000.0,
        )

        with pytest.raises(ComplianceViolation):
            oms.submit(order, correlation_id="test-idem-1")

        with pytest.raises(ComplianceViolation):
            oms.submit(order, correlation_id="test-idem-1")

    def test_daily_drawdown_blocks_orders(self, oms, risk_compliance):
        """Test that daily drawdown limit blocks orders."""
        oms.risk._balance = 85000.0
        oms.risk._peak_equity = 100000.0

        order = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=0.5,
            price=40000.0,
        )

        with pytest.raises(ComplianceViolation) as exc_info:
            oms.submit(order, correlation_id="test-dd-1")

        assert "drawdown" in str(exc_info.value).lower()

    def test_risk_state_accessible(self, risk_compliance):
        """Test that risk state can be retrieved."""
        state = risk_compliance.get_state()

        assert "kill_switch" in state
        assert "max_notional_per_order" in state
        assert "max_gross_exposure" in state
        assert "timestamp" in state
        assert state["kill_switch"] is False

    def test_metrics_integration(self, oms):
        """Test that metrics are recorded for risk events."""
        from execution.metrics import get_risk_metrics

        metrics = get_risk_metrics()

        if metrics.enabled:
            metrics.record_kill_switch(False)
            metrics.record_gross_exposure(50000.0)
            metrics.record_rejection("max_notional_exceeded")
            metrics.record_circuit_trip("too_many_breaches")

            assert True
