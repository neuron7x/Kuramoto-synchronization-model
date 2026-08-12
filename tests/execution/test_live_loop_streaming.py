# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import time
from queue import Empty, Queue

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import ExecutionConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import RiskLimits, RiskManager


class StreamingConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._queue: "Queue[dict[str, object]]" = Queue()
        self.fetch_calls = 0

    def connect(self, credentials=None) -> None:  # type: ignore[override]
        return None

    def disconnect(self) -> None:  # type: ignore[override]
        return None

    def next_event(self, timeout: float | None = None):
        try:
            if timeout is None:
                return self._queue.get()
            if timeout <= 0:
                return self._queue.get_nowait()
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def stream_is_healthy(self) -> bool:
        return True

    def fetch_order(self, order_id: str):  # type: ignore[override]
        self.fetch_calls += 1
        return super().fetch_order(order_id)

    def publish_event(self, event: dict[str, object]) -> None:
        self._queue.put(event)


@pytest.fixture()
def live_loop_config(tmp_path):
    return LiveLoopConfig(
        state_dir=tmp_path / "state",
        submission_interval=0.02,
        fill_poll_interval=0.05,
        heartbeat_interval=0.1,
    )


def test_live_loop_processes_streamed_fills_without_polling(live_loop_config) -> None:
    connector = StreamingConnector()
    risk_manager = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    loop = LiveExecutionLoop({"stream": connector}, risk_manager, config=live_loop_config)

    loop.start(cold_start=True)
    try:
        order = Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.5,
            price=20_000.0,
            order_type=OrderType.LIMIT,
        )
        loop.submit_order("stream", order, correlation_id="stream-order")

        order_id = None
        for _ in range(50):
            outstanding = list(loop._contexts["stream"].oms.outstanding())
            if outstanding and outstanding[0].order_id:
                order_id = outstanding[0].order_id
                break
            time.sleep(0.05)
        assert order_id is not None

        connector.publish_event(
            {
                "type": "fill",
                "order_id": order_id,
                "filled_qty": order.quantity,
                "fill_price": order.price,
                "status": "FILLED",
                "cumulative_qty": order.quantity,
                "average_price": order.price,
            }
        )

        for _ in range(50):
            stored = loop._contexts["stream"].oms._orders.get(order_id)  # type: ignore[attr-defined]
            if stored and stored.status is OrderStatus.FILLED:
                break
            time.sleep(0.05)

        stored = loop._contexts["stream"].oms._orders.get(order_id)  # type: ignore[attr-defined]
        assert stored is not None
        assert stored.status is OrderStatus.FILLED
        assert stored.filled_quantity == pytest.approx(order.quantity)
        assert connector.fetch_calls == 0
    finally:
        loop.shutdown()
