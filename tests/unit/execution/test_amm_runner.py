# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from execution.amm_runner import AMMRunner


class DummyTimer:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> None:
        self.entered = True
        return None

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.exited = True
        return False


@pytest.mark.asyncio
async def test_on_tick_publishes_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    ports: list[int] = []
    monkeypatch.setattr("execution.amm_runner.start_http_server", lambda port: ports.append(port))
    timer = DummyTimer()
    monkeypatch.setattr("execution.amm_runner.timed_update", lambda *args, **kwargs: timer)
    calls: list[tuple] = []

    def fake_publish(
        symbol: str, tf: str, out: dict, k: float, theta: float, q_hi: float | None
    ) -> None:
        calls.append((symbol, tf, out, k, theta, q_hi))

    monkeypatch.setattr("execution.amm_runner.publish_metrics", fake_publish)

    runner = AMMRunner("BTC-USD", "1m", metrics_port=9100)
    result = await runner.on_tick(0.01, 0.6, 0.1, None)

    assert ports == [9100]
    assert timer.entered and timer.exited
    assert "amm_pulse" in result and "amm_precision" in result
    assert calls and calls[0][0] == "BTC-USD" and calls[0][1] == "1m"
    assert pytest.approx(calls[0][3], rel=1e-6) == runner.amm.gain
    assert pytest.approx(calls[0][4], rel=1e-6) == runner.amm.threshold


@pytest.mark.asyncio
async def test_run_stream_yields_each_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("execution.amm_runner.start_http_server", lambda port: None)
    monkeypatch.setattr("execution.amm_runner.timed_update", lambda *args, **kwargs: DummyTimer())
    monkeypatch.setattr("execution.amm_runner.publish_metrics", lambda *args, **kwargs: None)

    runner = AMMRunner("ETH-USD", "5m")

    async def gen():
        for i in range(3):
            yield 0.001 * i, 0.5, 0.0, None

    outputs = []
    async for out in runner.run_stream(gen()):
        outputs.append(out["amm_pulse"])

    assert len(outputs) == 3
    assert all(isinstance(v, float) for v in outputs)
