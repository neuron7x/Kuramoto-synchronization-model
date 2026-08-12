# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from domain import Signal, SignalAction


def test_signal_validation_enforces_confidence_range() -> None:
    with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
        Signal(symbol="BTCUSD", action=SignalAction.BUY, confidence=1.5)


def test_signal_to_dict_round_trips_metadata() -> None:
    signal = Signal(
        symbol="ETHUSD",
        action=SignalAction.SELL,
        confidence=0.7,
        rationale="overbought",
        metadata={"indicator": "rsi"},
    )
    payload = signal.to_dict()
    assert payload["symbol"] == "ETHUSD"
    assert payload["action"] == SignalAction.SELL.value
    assert payload["metadata"] == {"indicator": "rsi"}

    boosted = signal.with_confidence(0.9)
    assert boosted.confidence == pytest.approx(0.9)
    assert boosted.metadata == signal.metadata
