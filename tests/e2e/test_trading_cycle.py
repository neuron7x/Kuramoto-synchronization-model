"""E2E tests covering the trading lifecycle from data to execution."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from application.system import (
    ExchangeAdapterConfig,
    LiveLoopSettings,
    TradePulseSystem,
    TradePulseSystemConfig,
)
from domain import OrderSide, OrderStatus, SignalAction
from execution.connectors import BinanceConnector


@pytest.mark.slow
def test_end_to_end_trading_cycle(tmp_path: Path) -> None:
    """Simulate ingest → signal → execution on deterministic sandbox data."""

    data_path = Path(__file__).resolve().parents[2] / "data" / "sample.csv"

    connector = BinanceConnector()
    system = TradePulseSystem(
        TradePulseSystemConfig(
            venues=[ExchangeAdapterConfig(name="BINANCE", connector=connector)],
            live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
        )
    )

    market_frame = system.ingest_csv(
        data_path,
        symbol="BTCUSDT",
        venue="BINANCE",
        timestamp_field="ts",
        price_field="price",
        volume_field="volume",
    )
    assert not market_frame.empty
    assert market_frame.index.tz is not None

    feature_frame = system.build_feature_frame(market_frame)
    assert system.feature_pipeline.config.price_col in feature_frame
    assert "rsi" in feature_frame.columns

    def adaptive_momentum(prices: np.ndarray) -> np.ndarray:
        centred = prices - float(prices.mean())
        scale = float(prices.std()) or 1.0
        scores = np.tanh(centred / scale)
        if np.allclose(scores, 0.0):
            scores[-1] = 1.0
        elif abs(scores[-1]) < 1e-6:
            direction = scores[-2] if scores.size > 1 else 1.0
            if abs(direction) < 1e-6:
                direction = 1.0
            scores[-1] = np.sign(direction) * 0.5
        return scores

    signals = system.generate_signals(feature_frame, strategy=adaptive_momentum)
    assert signals
    actionable = [
        signal for signal in signals if signal.action is not SignalAction.HOLD
    ]
    assert actionable

    latest_signal = actionable[-1]
    latest_timestamp = pd.Timestamp(latest_signal.timestamp)
    latest_row = feature_frame.loc[latest_timestamp]
    price_col = system.feature_pipeline.config.price_col
    latest_price = float(latest_row[price_col])

    # Round-trip through DTO conversion to ensure metadata survives transport.
    payloads = system.signals_to_dtos([latest_signal])
    assert payloads[0]["symbol"] == "BTCUSDT"
    assert payloads[0]["metadata"]["score"] == pytest.approx(
        latest_signal.metadata["score"]
    )

    loop = system.ensure_live_loop()
    system.submit_signal(
        latest_signal,
        venue="BINANCE",
        quantity=0.25,
        price=latest_price,
    )

    context = loop._contexts["binance"]
    submitted_order = context.oms.process_next()
    assert submitted_order.order_id is not None
    assert submitted_order.status is OrderStatus.OPEN
    assert connector.fetch_order(submitted_order.order_id).status is OrderStatus.OPEN

    # Emulate a full fill to complete the trade lifecycle.
    fill_qty = submitted_order.quantity
    context.oms.register_fill(submitted_order.order_id, fill_qty, latest_price)
    filled_order = connector.fetch_order(submitted_order.order_id)
    assert filled_order.status is OrderStatus.FILLED
    assert filled_order.filled_quantity == pytest.approx(fill_qty)

    if submitted_order.side is OrderSide.BUY:
        expected_position = fill_qty
    else:
        expected_position = -fill_qty

    assert system.risk_manager.current_position("BTCUSDT") == pytest.approx(
        expected_position
    )
    assert system.risk_manager.current_notional("BTCUSDT") == pytest.approx(
        abs(expected_position * latest_price)
    )

    assert system.last_execution_submission_at is not None
    assert system.last_execution_error is None
    assert not list(connector.open_orders())  # Filled orders should not remain active.
