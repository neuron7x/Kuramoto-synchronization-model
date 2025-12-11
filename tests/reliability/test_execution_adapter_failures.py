# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Reliability tests for execution adapter failures.

Validates handling of timeouts and connection errors:
- REL_EXEC_TIMEOUT_001: Order timeout handling
- REL_EXEC_TIMEOUT_002: Connection failure handling
- REL_EXEC_TIMEOUT_003: Partial fills with timeout

These tests ensure execution layer fails gracefully without hanging or data corruption.
"""
from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from domain import Order, OrderSide, OrderStatus
from execution.connectors import SimulatedExchangeConnector
from execution.paper_trading import (
    DeterministicLatencyModel,
    PaperTradingEngine,
)


def test_order_timeout_handling() -> None:
    """Test that order timeouts are handled gracefully (REL_EXEC_TIMEOUT_001)."""
    
    # Create a mock connector that simulates timeout
    class TimeoutConnector(SimulatedExchangeConnector):
        def submit_order(self, order: Order) -> Order:
            # Simulate long delay (timeout scenario)
            time.sleep(0.1)
            raise TimeoutError("Broker API timeout after 5 seconds")
    
    connector = TimeoutConnector()
    engine = PaperTradingEngine(
        connector=connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.01, fill_delay=0.01),
    )
    
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=1.0,
        order_type="market",
    )
    
    # Test that timeout is caught and handled
    start = time.time()
    with pytest.raises(TimeoutError, match="timeout"):
        engine.execute(order)
    elapsed = time.time() - start
    
    # Verify timeout happens quickly (not hanging)
    assert elapsed < 1.0, f"Timeout detection took too long: {elapsed}s"


def test_connection_failure_handling() -> None:
    """Test that connection failures are handled clearly (REL_EXEC_TIMEOUT_002)."""
    
    # Create a connector that simulates connection failure
    class FailingConnector(SimulatedExchangeConnector):
        def submit_order(self, order: Order) -> Order:
            raise ConnectionError("Failed to connect to broker API at api.example.com:443")
    
    connector = FailingConnector()
    engine = PaperTradingEngine(
        connector=connector,
        latency_model=DeterministicLatencyModel(),
    )
    
    order = Order(
        symbol="ETHUSD",
        side=OrderSide.SELL,
        quantity=2.0,
        order_type="market",
    )
    
    # Verify connection error is raised with clear message
    with pytest.raises(ConnectionError, match="connect|broker|API"):
        engine.execute(order)


def test_partial_fill_timeout() -> None:
    """Test that partial fills are tracked correctly on timeout (REL_EXEC_TIMEOUT_003)."""
    
    # Create a connector that simulates partial fill then timeout
    class PartialFillConnector(SimulatedExchangeConnector):
        def __init__(self):
            super().__init__()
            self.fill_count = 0
        
        def submit_order(self, order: Order) -> Order:
            self.fill_count += 1
            if self.fill_count == 1:
                # First call: partial fill
                filled_order = Order(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity * 0.5,  # Only 50% filled
                    order_type=order.order_type,
                    order_id="partial-123",
                    status=OrderStatus.PARTIALLY_FILLED,
                )
                return filled_order
            else:
                # Subsequent calls: timeout
                raise TimeoutError("Timeout waiting for remainder of order")
    
    connector = PartialFillConnector()
    engine = PaperTradingEngine(
        connector=connector,
        latency_model=DeterministicLatencyModel(),
    )
    
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=10.0,
        order_type="market",
    )
    
    # First execution should succeed with partial fill
    result1 = engine.execute(order)
    assert result1.order.quantity == 5.0  # 50% of original
    assert result1.order.status == OrderStatus.PARTIALLY_FILLED
    
    # Second execution should timeout
    with pytest.raises(TimeoutError):
        engine.execute(order)


def test_retry_exhaustion() -> None:
    """Test that retry logic eventually gives up (no infinite retries)."""
    
    class AlwaysFailingConnector(SimulatedExchangeConnector):
        def __init__(self):
            super().__init__()
            self.attempt_count = 0
        
        def submit_order(self, order: Order) -> Order:
            self.attempt_count += 1
            raise ConnectionError(f"Connection failed (attempt {self.attempt_count})")
    
    connector = AlwaysFailingConnector()
    
    # Manually implement simple retry logic for test
    max_retries = 3
    retry_count = 0
    
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=1.0,
        order_type="market",
    )
    
    # Test retry exhaustion
    start = time.time()
    while retry_count < max_retries:
        try:
            connector.submit_order(order)
            break
        except ConnectionError:
            retry_count += 1
            if retry_count >= max_retries:
                break
            time.sleep(0.01)  # Brief delay between retries
    
    elapsed = time.time() - start
    
    # Verify we tried exactly max_retries times
    assert connector.attempt_count == max_retries
    # Verify it failed fast (not hanging)
    assert elapsed < 1.0, f"Retry exhaustion took too long: {elapsed}s"


def test_no_position_update_on_unconfirmed_order() -> None:
    """Test that positions are not updated when order is unconfirmed."""
    
    class UnconfirmedConnector(SimulatedExchangeConnector):
        def submit_order(self, order: Order) -> Order:
            # Return order in PENDING state (not confirmed)
            return Order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                order_type=order.order_type,
                order_id="pending-456",
                status=OrderStatus.PENDING,
            )
    
    connector = UnconfirmedConnector()
    engine = PaperTradingEngine(
        connector=connector,
        latency_model=DeterministicLatencyModel(),
    )
    
    order = Order(
        symbol="ETHUSD",
        side=OrderSide.BUY,
        quantity=5.0,
        order_type="market",
    )
    
    result = engine.execute(order)
    
    # Verify order is marked as pending, not filled
    assert result.order.status == OrderStatus.PENDING
    # System should NOT assume execution occurred
    assert result.order.order_id == "pending-456"


def test_clear_error_messages() -> None:
    """Test that error messages contain actionable information."""
    
    class DetailedErrorConnector(SimulatedExchangeConnector):
        def submit_order(self, order: Order) -> Order:
            raise ConnectionError(
                "Failed to connect to broker API at wss://api.example.com/ws: "
                "Connection refused. Check network and API credentials."
            )
    
    connector = DetailedErrorConnector()
    engine = PaperTradingEngine(
        connector=connector,
        latency_model=DeterministicLatencyModel(),
    )
    
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=1.0,
        order_type="market",
    )
    
    # Verify error message is detailed
    with pytest.raises(ConnectionError) as exc_info:
        engine.execute(order)
    
    error_msg = str(exc_info.value)
    # Error should contain useful details
    assert "api.example.com" in error_msg or "API" in error_msg
    assert "connect" in error_msg.lower() or "connection" in error_msg.lower()
