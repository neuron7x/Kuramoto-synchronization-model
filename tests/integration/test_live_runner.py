# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests covering the live trading runner wiring."""

from __future__ import annotations

import time
from pathlib import Path

from domain import Order, OrderSide, OrderType
from execution.connectors import BinanceConnector
from interfaces.live_runner import LiveTradingRunner


def _write_config(path: Path, state_dir: Path) -> None:
    contents = f"""
    [loop]
    state_dir = "{state_dir.as_posix()}"
    submission_interval = 0.05
    fill_poll_interval = 0.05
    heartbeat_interval = 0.1
    max_backoff = 0.2

    [risk]
    max_notional = 100000.0
    max_position = 10.0
    max_orders_per_interval = 50
    interval_seconds = 1.0

    [[venues]]
    name = "binance"
    class = "execution.connectors.BinanceConnector"
    sandbox = true
    """
    path.write_text(contents, encoding="utf-8")


def _wait_for(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition was not met within timeout")


def test_runner_cold_start_and_reconciliation(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    config_path = tmp_path / "live.toml"
    _write_config(config_path, state_dir)

    runner = LiveTradingRunner(config_path)

    try:
        runner.start(cold_start=True)
        snapshots_dir = state_dir / "session_snapshots"
        first_start_snapshots = sorted(snapshots_dir.glob("*.json"))
        assert first_start_snapshots
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.1,
            price=20_000,
            order_type=OrderType.LIMIT,
        )
        runner.loop.submit_order("binance", order, correlation_id="ord-1")

        def has_outstanding() -> bool:
            outstanding = runner.loop._contexts["binance"].oms.outstanding()
            return any(o.order_id for o in outstanding)

        _wait_for(has_outstanding)
    finally:
        runner.shutdown()

    connector = runner.connectors["binance"]
    assert isinstance(connector, BinanceConnector)
    stray = connector.place_order(
        Order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=0.2,
            price=20_100,
            order_type=OrderType.LIMIT,
        )
    )

    runner.start(cold_start=False)

    try:
        second_start_snapshots = sorted((state_dir / "session_snapshots").glob("*.json"))
        assert len(second_start_snapshots) > len(first_start_snapshots)

        def adopted() -> bool:
            outstanding = runner.loop._contexts["binance"].oms.outstanding()
            return any(o.order_id == stray.order_id for o in outstanding)

        _wait_for(adopted)
        assert runner.kill_switch_reason is None
    finally:
        runner.request_stop("test")
        runner.shutdown()
