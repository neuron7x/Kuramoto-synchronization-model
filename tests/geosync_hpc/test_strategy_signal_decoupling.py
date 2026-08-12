# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression guard for the HPCAIStrategy signal-emission contract.

Before this fix, ``HPCAIStrategy.on_market_data`` constructed
``backtest.events.SignalEvent`` with ``signal_type``/``strength``/``price``
keyword arguments. Those names only exist on the simplified *mock* class used
when the backtest package is unavailable; the real event-driven
``SignalEvent.__init__`` is ``(symbol, target_position, step)``. So whenever
the backtest package *was* importable (the normal case), emitting a BUY/SELL
signal raised ``TypeError`` inside the strategy. The fix introduces a
dedicated, decoupled :class:`StrategySignal`. CodeQL py/call/wrong-named-class-argument
#346 / #347.
"""

from __future__ import annotations

import numpy as np

from geosync_hpc.hpc_real_data_backtest import HPCAIStrategy, StrategySignal


class _StubModel:
    """Minimal model that always votes BUY; no HPC machinery required."""

    def __init__(self, action: int) -> None:
        self._action = action

    def decide_action(self, data: object, prev_pwpe: float) -> int:
        return self._action

    def get_pwpe(self, data: object) -> float:
        return 0.0


class _Event:
    def __init__(self, symbol: str, price: float, step: int) -> None:
        self.symbol = symbol
        self.price = price
        self.step = step
        self.volume = 1_000_000.0


def _drive(strategy: HPCAIStrategy) -> StrategySignal | None:
    signal = None
    prices = np.linspace(100.0, 110.0, strategy.lookback_window + 1)
    for i, price in enumerate(prices):
        signal = strategy.on_market_data(_Event("ASSET", float(price), i))
    return signal


def test_buy_emits_strategy_signal_not_backtest_event() -> None:
    """A BUY decision yields a StrategySignal — the call path that used to
    crash with the real backtest.events.SignalEvent constructor."""
    strategy = HPCAIStrategy(model=_StubModel(action=1), lookback_window=8, position_size=0.25)
    signal = _drive(strategy)
    assert isinstance(signal, StrategySignal)
    assert signal.signal_type == "LONG"
    assert signal.strength == 0.25
    assert signal.symbol == "ASSET"


def test_sell_emits_strategy_signal() -> None:
    strategy = HPCAIStrategy(model=_StubModel(action=2), lookback_window=8, position_size=0.25)
    signal = _drive(strategy)
    assert isinstance(signal, StrategySignal)
    assert signal.signal_type == "SHORT"


def test_hold_emits_no_signal() -> None:
    strategy = HPCAIStrategy(model=_StubModel(action=0), lookback_window=8)
    assert _drive(strategy) is None
