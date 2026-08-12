# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for the live execution loop orchestrator."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import BinanceConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import JsonRiskStateStore, LimitViolation, RiskLimits, RiskManager


class RecoveryConnector(BinanceConnector):
    def __init__(self) -> None:
        super().__init__()
        self.connected = False
        self.placements = 0

    def connect(self, credentials=None) -> None:  # type: ignore[override]
        self.connected = True

    def disconnect(self) -> None:  # type: ignore[override]
        self.connected = False

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:  # type: ignore[override]
        self.placements += 1
        return super().place_order(order, idempotency_key=idempotency_key)

    def drop_order(self, order_id: str) -> None:
        self._orders.pop(order_id, None)


class FlakyConnector(BinanceConnector):
    def __init__(self) -> None:
        super().__init__()
        self._failures_remaining = 2
        self.reconnects = 0

    def connect(self, credentials=None) -> None:  # type: ignore[override]
        self.reconnects += 1

    def get_positions(self):  # type: ignore[override]
        if self._failures_remaining > 0:
            self._failures_remaining -= 1
            raise ConnectionError("simulated heartbeat disconnect")
        return super().get_positions()


class WarmStartConnector(BinanceConnector):
    def __init__(self) -> None:
        super().__init__()
        self._seeded: list[dict[str, float]] = []

    def seed_position(self, symbol: str, quantity: float, price: float) -> None:
        entry: dict[str, float] = {
            "symbol": symbol,
            "net_quantity": quantity,
            "average_price": price,
            "price": price,
        }
        if quantity > 0:
            entry["long_quantity"] = quantity
            entry["long_average_price"] = price
        elif quantity < 0:
            entry["short_quantity"] = abs(quantity)
            entry["short_average_price"] = price
        self._seeded = [entry]

    def get_positions(self):  # type: ignore[override]
        base = list(super().get_positions())
        return base + list(self._seeded)


@pytest.fixture()
def live_loop_config(tmp_path: Path) -> LiveLoopConfig:
    return LiveLoopConfig(
        state_dir=tmp_path / "state",
        submission_interval=0.05,
        fill_poll_interval=0.05,
        heartbeat_interval=0.1,
        max_backoff=0.2,
    )


def test_live_loop_recovers_and_requeues_orders(
    live_loop_config: LiveLoopConfig,
) -> None:
    connector = RecoveryConnector()
    risk_manager = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=live_loop_config)

    loop.start(cold_start=True)
    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.2,
        price=20_000,
        order_type=OrderType.LIMIT,
    )
    loop.submit_order("binance", order, correlation_id="ord-1")

    order_id: str | None = None
    for _ in range(50):
        pending = [o for o in loop._contexts["binance"].oms.outstanding() if o.order_id]
        if pending:
            order_id = pending[0].order_id
            break
        time.sleep(0.05)
    assert order_id is not None

    loop.shutdown()

    assert connector.placements == 1
    connector.drop_order(order_id)
    stray = connector.place_order(
        Order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=0.1,
            price=20_100,
            order_type=OrderType.LIMIT,
        )
    )

    restart_risk = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    loop_restart = LiveExecutionLoop({"binance": connector}, restart_risk, config=live_loop_config)
    loop_restart.start(cold_start=False)

    for _ in range(50):
        if connector.placements >= 2:
            break
        time.sleep(0.05)
    assert connector.placements >= 2

    adopted_ids = [
        o.order_id for o in loop_restart._contexts["binance"].oms.outstanding() if o.order_id
    ]
    assert stray.order_id in adopted_ids

    loop_restart.shutdown()


def test_live_loop_creates_session_snapshot(
    live_loop_config: LiveLoopConfig,
) -> None:
    connector = BinanceConnector()
    risk_manager = RiskManager(RiskLimits(max_notional=100_000.0, max_position=10.0))
    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=live_loop_config)

    loop.start(cold_start=True)
    try:
        snapshot_dir = live_loop_config.state_dir / "session_snapshots"
        files = sorted(snapshot_dir.glob("*.json"))
        assert files
        payload = json.loads(files[-1].read_text())
        assert payload["mode"] == "live"
        assert payload["risk_limits"]["max_position"] == 10.0
        assert "hash" in payload
    finally:
        loop.shutdown()


def test_live_loop_warm_start_enforces_limits(live_loop_config: LiveLoopConfig) -> None:
    connector = WarmStartConnector()
    state_path = live_loop_config.state_dir / "risk_state.json"
    store = JsonRiskStateStore(state_path)
    limits = RiskLimits(max_notional=1_000_000, max_position=1.0)
    risk_manager = RiskManager(limits, risk_state_store=store)

    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=live_loop_config)
    loop.start(cold_start=True)
    try:
        risk_manager.register_fill("BTCUSDT", "buy", 0.8, 20_000)
        connector.seed_position("BTCUSDT", 0.8, 20_000)
    finally:
        loop.shutdown()

    restart_risk = RiskManager(limits, risk_state_store=store)
    loop_restart = LiveExecutionLoop({"binance": connector}, restart_risk, config=live_loop_config)
    loop_restart.start(cold_start=False)
    try:
        aggressive = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.4,
            price=19_900,
            order_type=OrderType.LIMIT,
        )
        with pytest.raises(LimitViolation):
            loop_restart.submit_order("binance", aggressive, correlation_id="warm-1")
    finally:
        loop_restart.shutdown()


def test_live_loop_emits_reconnect_on_heartbeat_failure(
    live_loop_config: LiveLoopConfig,
) -> None:
    connector = FlakyConnector()
    risk_manager = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=live_loop_config)

    reconnect_events: list[tuple[str, int]] = []

    def on_reconnect(venue: str, attempt: int, delay: float, exc: Exception | None) -> None:
        reconnect_events.append((venue, attempt))

    loop.on_reconnect.connect(on_reconnect)
    loop.start(cold_start=True)

    for _ in range(50):
        if reconnect_events:
            break
        time.sleep(0.05)

    loop.shutdown()

    assert reconnect_events, "Expected at least one reconnect event to be emitted"
    venue, attempt = reconnect_events[0]
    assert venue == "binance"
    assert attempt >= 1
    assert connector.reconnects >= 1


def test_live_loop_cancel_and_kill_switch_flushes_orders(
    live_loop_config: LiveLoopConfig,
) -> None:
    connector = RecoveryConnector()
    risk_manager = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=live_loop_config)

    loop.start(cold_start=True)

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.15,
        price=19_500,
        order_type=OrderType.LIMIT,
    )
    loop.submit_order("binance", order, correlation_id="ord-cancel-1")

    def _wait_for_order_id() -> str:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            outstanding = [
                o for o in loop._contexts["binance"].oms.outstanding() if o.order_id is not None
            ]
            if outstanding:
                order_id = outstanding[0].order_id
                assert order_id is not None
                return order_id
            time.sleep(0.05)
        raise AssertionError("order was not acknowledged in time")

    first_order_id = _wait_for_order_id()
    assert loop.cancel_order(first_order_id)
    assert all(o.order_id != first_order_id for o in loop._contexts["binance"].oms.outstanding())
    assert not connector.fetch_order(first_order_id).is_active
    assert loop.cancel_order("missing", venue="binance") is False

    replacement = Order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=0.05,
        price=20_050,
        order_type=OrderType.LIMIT,
    )
    loop.submit_order("binance", replacement, correlation_id="ord-kill-1")
    replacement_id = _wait_for_order_id()

    risk_manager.kill_switch.trigger("panic-stop")

    def _no_outstanding() -> bool:
        return not any(loop._contexts["binance"].oms.outstanding())

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _no_outstanding() and loop._stop.is_set():
            break
        time.sleep(0.05)

    assert loop._kill_notified is True
    assert loop._stop.is_set()
    assert _no_outstanding()
    assert not connector.fetch_order(replacement_id).is_active

    loop.shutdown()
