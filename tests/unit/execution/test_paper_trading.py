# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive Unit Tests for Paper Trading Engine.

This module provides thorough test coverage for the paper trading engine,
including latency simulation, fill handling, and execution quality analysis.

Tests cover:
- LatencySample value object
- DeterministicLatencyModel
- TelemetryEvent tracking
- FillEvent handling
- PnLAnalysis calculations
- PaperOrderReport generation
- PaperTradingEngine execution flow
"""

from __future__ import annotations

import pytest

from domain import Order, OrderSide, OrderStatus
from execution.connectors import SimulatedExchangeConnector
from execution.paper_trading import (
    DeterministicLatencyModel,
    FillEvent,
    LatencySample,
    PaperOrderReport,
    PaperTradingEngine,
    PnLAnalysis,
    TelemetryEvent,
)

# ============================================================================
# LatencySample Tests
# ============================================================================


class TestLatencySample:
    """Test suite for LatencySample dataclass."""

    def test_latency_sample_initialization(self) -> None:
        """Test LatencySample initializes with valid values."""
        sample = LatencySample(ack_delay=0.1, fill_delay=0.2)
        assert sample.ack_delay == 0.1
        assert sample.fill_delay == 0.2

    def test_latency_sample_total_delay(self) -> None:
        """Test total_delay property computes correct sum."""
        sample = LatencySample(ack_delay=0.1, fill_delay=0.2)
        assert sample.total_delay == pytest.approx(0.3)

    def test_latency_sample_zero_delays(self) -> None:
        """Test LatencySample accepts zero delays."""
        sample = LatencySample(ack_delay=0.0, fill_delay=0.0)
        assert sample.total_delay == 0.0

    def test_latency_sample_negative_ack_delay_raises(self) -> None:
        """Test LatencySample rejects negative ack_delay."""
        with pytest.raises(ValueError, match="non-negative"):
            LatencySample(ack_delay=-0.1, fill_delay=0.0)

    def test_latency_sample_negative_fill_delay_raises(self) -> None:
        """Test LatencySample rejects negative fill_delay."""
        with pytest.raises(ValueError, match="non-negative"):
            LatencySample(ack_delay=0.0, fill_delay=-0.1)

    def test_latency_sample_immutable(self) -> None:
        """Test LatencySample is frozen (immutable)."""
        sample = LatencySample(ack_delay=0.1, fill_delay=0.2)
        with pytest.raises(AttributeError):
            sample.ack_delay = 0.5  # type: ignore[misc]


# ============================================================================
# DeterministicLatencyModel Tests
# ============================================================================


class TestDeterministicLatencyModel:
    """Test suite for DeterministicLatencyModel."""

    def test_default_initialization(self) -> None:
        """Test DeterministicLatencyModel defaults to zero delays."""
        model = DeterministicLatencyModel()
        assert model.ack_delay == 0.0
        assert model.fill_delay == 0.0

    def test_custom_delays(self) -> None:
        """Test DeterministicLatencyModel accepts custom delays."""
        model = DeterministicLatencyModel(ack_delay=0.05, fill_delay=0.1)
        assert model.ack_delay == 0.05
        assert model.fill_delay == 0.1

    def test_sample_returns_latency_sample(self) -> None:
        """Test sample() returns correct LatencySample."""
        model = DeterministicLatencyModel(ack_delay=0.05, fill_delay=0.1)
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        sample = model.sample(order)

        assert isinstance(sample, LatencySample)
        assert sample.ack_delay == 0.05
        assert sample.fill_delay == 0.1

    def test_sample_consistent_across_orders(self) -> None:
        """Test that different orders get the same latency."""
        model = DeterministicLatencyModel(ack_delay=0.1, fill_delay=0.2)
        order1 = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)
        order2 = Order(symbol="ETHUSD", side=OrderSide.SELL, quantity=10.0)

        sample1 = model.sample(order1)
        sample2 = model.sample(order2)

        assert sample1.total_delay == sample2.total_delay

    def test_negative_ack_delay_raises(self) -> None:
        """Test DeterministicLatencyModel rejects negative ack_delay."""
        with pytest.raises(ValueError, match="non-negative"):
            DeterministicLatencyModel(ack_delay=-0.1)

    def test_negative_fill_delay_raises(self) -> None:
        """Test DeterministicLatencyModel rejects negative fill_delay."""
        with pytest.raises(ValueError, match="non-negative"):
            DeterministicLatencyModel(fill_delay=-0.1)


# ============================================================================
# TelemetryEvent Tests
# ============================================================================


class TestTelemetryEvent:
    """Test suite for TelemetryEvent dataclass."""

    def test_telemetry_event_initialization(self) -> None:
        """Test TelemetryEvent initializes correctly."""
        event = TelemetryEvent(
            timestamp=1000.0,
            event="order.submit",
            attributes={"symbol": "BTCUSD"},
        )
        assert event.timestamp == 1000.0
        assert event.event == "order.submit"
        assert event.attributes == {"symbol": "BTCUSD"}

    def test_telemetry_event_immutable(self) -> None:
        """Test TelemetryEvent is frozen (immutable)."""
        event = TelemetryEvent(
            timestamp=1000.0,
            event="order.submit",
            attributes={},
        )
        with pytest.raises(AttributeError):
            event.timestamp = 2000.0  # type: ignore[misc]


# ============================================================================
# FillEvent Tests
# ============================================================================


class TestFillEvent:
    """Test suite for FillEvent dataclass."""

    def test_fill_event_initialization(self) -> None:
        """Test FillEvent initializes correctly."""
        fill = FillEvent(quantity=1.5, price=50000.0, timestamp=1000.0)
        assert fill.quantity == 1.5
        assert fill.price == 50000.0
        assert fill.timestamp == 1000.0

    def test_fill_event_immutable(self) -> None:
        """Test FillEvent is frozen (immutable)."""
        fill = FillEvent(quantity=1.0, price=100.0, timestamp=0.0)
        with pytest.raises(AttributeError):
            fill.quantity = 2.0  # type: ignore[misc]


# ============================================================================
# PnLAnalysis Tests
# ============================================================================


class TestPnLAnalysis:
    """Test suite for PnLAnalysis dataclass."""

    def test_pnl_analysis_initialization(self) -> None:
        """Test PnLAnalysis initializes correctly."""
        pnl = PnLAnalysis(
            realized_value=50000.0,
            ideal_value=50100.0,
            deviation=-100.0,
            implementation_shortfall=0.002,
        )
        assert pnl.realized_value == 50000.0
        assert pnl.ideal_value == 50100.0
        assert pnl.deviation == -100.0
        assert pnl.implementation_shortfall == pytest.approx(0.002)

    def test_pnl_analysis_immutable(self) -> None:
        """Test PnLAnalysis is frozen (immutable)."""
        pnl = PnLAnalysis(
            realized_value=50000.0,
            ideal_value=50100.0,
            deviation=-100.0,
            implementation_shortfall=0.002,
        )
        with pytest.raises(AttributeError):
            pnl.realized_value = 51000.0  # type: ignore[misc]


# ============================================================================
# PaperOrderReport Tests
# ============================================================================


class TestPaperOrderReport:
    """Test suite for PaperOrderReport dataclass."""

    @pytest.fixture
    def sample_order(self) -> Order:
        """Create a sample order for testing."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)
        order.mark_submitted("test-order-1")
        order.record_fill(1.0, 50000.0)
        return order

    @pytest.fixture
    def sample_report(self, sample_order: Order) -> PaperOrderReport:
        """Create a sample report for testing."""
        return PaperOrderReport(
            order=sample_order,
            latency=LatencySample(ack_delay=0.01, fill_delay=0.02),
            fills=(FillEvent(quantity=1.0, price=50000.0, timestamp=100.0),),
            telemetry=(TelemetryEvent(timestamp=100.0, event="order.submit", attributes={}),),
            pnl=PnLAnalysis(
                realized_value=50000.0,
                ideal_value=50000.0,
                deviation=0.0,
                implementation_shortfall=0.0,
            ),
            stability_issues=(),
        )

    def test_report_order_id_property(self, sample_report: PaperOrderReport) -> None:
        """Test order_id property returns correct value."""
        assert sample_report.order_id == "test-order-1"

    def test_report_contains_fills(self, sample_report: PaperOrderReport) -> None:
        """Test report contains fill events."""
        assert len(sample_report.fills) == 1
        assert sample_report.fills[0].quantity == 1.0

    def test_report_contains_telemetry(self, sample_report: PaperOrderReport) -> None:
        """Test report contains telemetry events."""
        assert len(sample_report.telemetry) >= 1

    def test_report_stability_issues_tuple(self, sample_report: PaperOrderReport) -> None:
        """Test stability_issues is a tuple."""
        assert isinstance(sample_report.stability_issues, tuple)


# ============================================================================
# PaperTradingEngine Tests
# ============================================================================


class TestPaperTradingEngine:
    """Test suite for PaperTradingEngine class."""

    @pytest.fixture
    def connector(self) -> SimulatedExchangeConnector:
        """Create a simulated exchange connector."""
        return SimulatedExchangeConnector(sandbox=True)

    @pytest.fixture
    def engine(self, connector: SimulatedExchangeConnector) -> PaperTradingEngine:
        """Create a paper trading engine with default settings."""
        return PaperTradingEngine(connector)

    @pytest.fixture
    def engine_with_latency(self, connector: SimulatedExchangeConnector) -> PaperTradingEngine:
        """Create a paper trading engine with latency model."""
        latency_model = DeterministicLatencyModel(ack_delay=0.01, fill_delay=0.02)
        return PaperTradingEngine(connector, latency_model=latency_model)

    def test_engine_initialization(self, connector: SimulatedExchangeConnector) -> None:
        """Test PaperTradingEngine initializes correctly."""
        engine = PaperTradingEngine(connector)
        assert engine is not None

    def test_engine_with_custom_clock(self, connector: SimulatedExchangeConnector) -> None:
        """Test engine accepts custom clock function."""
        clock_value = 1000.0
        engine = PaperTradingEngine(connector, clock=lambda: clock_value)
        assert engine is not None

    def test_execute_order_basic(self, engine: PaperTradingEngine) -> None:
        """Test basic order execution."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(order, execution_price=50000.0)

        assert isinstance(report, PaperOrderReport)
        assert report.order.status == OrderStatus.FILLED
        assert report.order.filled_quantity == 1.0

    def test_execute_order_sell_side(self, engine: PaperTradingEngine) -> None:
        """Test sell order execution."""
        order = Order(symbol="BTCUSD", side=OrderSide.SELL, quantity=2.0)

        report = engine.execute_order(order, execution_price=50000.0)

        assert report.order.side == OrderSide.SELL
        assert report.order.filled_quantity == 2.0

    def test_execute_order_with_ideal_price(self, engine: PaperTradingEngine) -> None:
        """Test order execution with ideal price for slippage calculation."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(
            order,
            execution_price=50100.0,
            ideal_price=50000.0,
        )

        # PnL should reflect slippage
        assert report.pnl.ideal_value != report.pnl.realized_value

    def test_execute_order_with_latency(self, engine_with_latency: PaperTradingEngine) -> None:
        """Test order execution with latency model."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine_with_latency.execute_order(order, execution_price=50000.0)

        # Latency should be recorded
        assert report.latency.ack_delay == 0.01
        assert report.latency.fill_delay == 0.02

    def test_execute_order_records_telemetry(self, engine: PaperTradingEngine) -> None:
        """Test that telemetry events are recorded."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(order, execution_price=50000.0)

        # Should have submit, ack, and fill events
        event_types = [e.event for e in report.telemetry]
        assert "order.submit" in event_types
        assert "order.ack" in event_types
        assert "order.fill" in event_types

    def test_execute_order_invalid_execution_price_raises(self, engine: PaperTradingEngine) -> None:
        """Test that zero execution price raises ValueError."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        with pytest.raises(ValueError, match="execution_price must be positive"):
            engine.execute_order(order, execution_price=0.0)

    def test_execute_order_negative_execution_price_raises(
        self, engine: PaperTradingEngine
    ) -> None:
        """Test that negative execution price raises ValueError."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        with pytest.raises(ValueError, match="execution_price must be positive"):
            engine.execute_order(order, execution_price=-100.0)

    def test_execute_order_invalid_ideal_price_raises(self, engine: PaperTradingEngine) -> None:
        """Test that zero ideal price raises ValueError."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        with pytest.raises(ValueError, match="ideal_price must be positive"):
            engine.execute_order(order, execution_price=50000.0, ideal_price=0.0)

    def test_execute_order_with_metadata(self, engine: PaperTradingEngine) -> None:
        """Test order execution with metadata."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(
            order,
            execution_price=50000.0,
            metadata={"strategy": "momentum", "signal_strength": 0.8},
        )

        # Check that metadata is recorded in telemetry
        submit_event = next(e for e in report.telemetry if e.event == "order.submit")
        assert "metadata" in submit_event.attributes

    def test_execute_order_with_idempotency_key(self, engine: PaperTradingEngine) -> None:
        """Test order execution with idempotency key."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(
            order,
            execution_price=50000.0,
            idempotency_key="unique-order-123",
        )

        assert report.order_id is not None

    def test_execute_order_partial_quantity(self, engine: PaperTradingEngine) -> None:
        """Test order execution with partial quantity."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=10.0)

        report = engine.execute_order(
            order,
            execution_price=50000.0,
            executed_quantity=5.0,  # Only fill 5 of 10
        )

        # Should fill only the specified quantity
        assert report.order.filled_quantity == 5.0
        assert report.order.status == OrderStatus.PARTIALLY_FILLED

    def test_telemetry_listener_callback(self, connector: SimulatedExchangeConnector) -> None:
        """Test that telemetry listeners are called."""
        events_received: list[TelemetryEvent] = []

        def listener(event: TelemetryEvent) -> None:
            events_received.append(event)

        engine = PaperTradingEngine(connector, telemetry_listeners=[listener])
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        engine.execute_order(order, execution_price=50000.0)

        # Listener should have received events
        assert len(events_received) >= 3  # submit, ack, fill

    def test_pnl_calculation_buy_order(self, engine: PaperTradingEngine) -> None:
        """Test PnL calculation for buy order."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(
            order,
            execution_price=50000.0,
            ideal_price=49000.0,  # Paid more than ideal
        )

        # For buy: side_factor = 1.0
        # realized_value = 1.0 * 1.0 * 50000.0 = 50000.0
        # ideal_value = 1.0 * 1.0 * 49000.0 = 49000.0
        # deviation = realized_value - ideal_value = 1000.0
        assert report.pnl.realized_value == pytest.approx(50000.0)
        assert report.pnl.ideal_value == pytest.approx(49000.0)
        assert report.pnl.deviation == pytest.approx(1000.0)

    def test_pnl_calculation_sell_order(self, engine: PaperTradingEngine) -> None:
        """Test PnL calculation for sell order."""
        order = Order(symbol="BTCUSD", side=OrderSide.SELL, quantity=1.0)

        report = engine.execute_order(
            order,
            execution_price=50000.0,
            ideal_price=51000.0,  # Sold for less than ideal
        )

        # For sell: side_factor = -1.0
        # realized_value = -1.0 * 1.0 * 50000.0 = -50000.0
        # ideal_value = -1.0 * 1.0 * 51000.0 = -51000.0
        # deviation = realized_value - ideal_value = -50000.0 - (-51000.0) = 1000.0
        assert report.pnl.realized_value == pytest.approx(-50000.0)
        assert report.pnl.ideal_value == pytest.approx(-51000.0)
        assert report.pnl.deviation == pytest.approx(1000.0)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestPaperTradingEdgeCases:
    """Test edge cases and error handling in paper trading."""

    @pytest.fixture
    def connector(self) -> SimulatedExchangeConnector:
        return SimulatedExchangeConnector(sandbox=True)

    @pytest.fixture
    def engine(self, connector: SimulatedExchangeConnector) -> PaperTradingEngine:
        return PaperTradingEngine(connector)

    def test_execute_order_with_zero_quantity_raises(self, engine: PaperTradingEngine) -> None:
        """Test that zero quantity order raises during execution."""
        # Order with zero quantity should fail at creation or execution
        with pytest.raises(ValueError):
            Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=0.0)

    def test_execute_order_negative_quantity_raises(self, engine: PaperTradingEngine) -> None:
        """Test that negative quantity order raises."""
        with pytest.raises(ValueError):
            Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=-1.0)

    def test_execute_order_exceeds_remaining_quantity_raises(
        self, engine: PaperTradingEngine
    ) -> None:
        """Test that executing more than remaining quantity raises."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        with pytest.raises(ValueError):
            engine.execute_order(
                order,
                execution_price=50000.0,
                executed_quantity=2.0,  # More than order quantity
            )

    def test_very_small_quantity(self, engine: PaperTradingEngine) -> None:
        """Test execution with very small quantity."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=0.0001)

        report = engine.execute_order(order, execution_price=50000.0)

        assert report.order.filled_quantity == 0.0001

    def test_very_large_price(self, engine: PaperTradingEngine) -> None:
        """Test execution with very large price."""
        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)

        report = engine.execute_order(order, execution_price=1_000_000.0)

        assert report.pnl.realized_value == pytest.approx(1_000_000.0)


# ============================================================================
# Custom Clock Tests
# ============================================================================


class TestPaperTradingWithCustomClock:
    """Test paper trading with custom clock for deterministic timing."""

    def test_clock_affects_timestamps(self) -> None:
        """Test that custom clock affects event timestamps."""
        connector = SimulatedExchangeConnector(sandbox=True)

        clock_time = 1000.0
        engine = PaperTradingEngine(connector, clock=lambda: clock_time)

        order = Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0)
        report = engine.execute_order(order, execution_price=50000.0)

        # Submit event should have the clock time
        submit_event = next(e for e in report.telemetry if e.event == "order.submit")
        assert submit_event.timestamp == clock_time
