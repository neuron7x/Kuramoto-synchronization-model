# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import datetime, timezone

import pytest

from application.trading import dto_to_signal


def test_dto_to_signal_parses_zulu_timestamp():
    payload = {
        "symbol": "BTCUSD",
        "action": "buy",
        "confidence": 0.75,
        "timestamp": "2024-01-01T15:30:00Z",
    }

    signal = dto_to_signal(payload)

    assert signal.symbol == "BTCUSD"
    assert signal.action.value == "buy"
    assert signal.timestamp == datetime(2024, 1, 1, 15, 30, tzinfo=timezone.utc)
    assert signal.confidence == pytest.approx(0.75)


def test_dto_to_signal_assumes_utc_for_naive_timestamp():
    payload = {
        "symbol": "ETHUSD",
        "action": "sell",
        "confidence": 0.5,
        "timestamp": "2024-05-10T12:00:00",  # no timezone information
    }

    signal = dto_to_signal(payload)

    assert signal.timestamp == datetime(2024, 5, 10, 12, 0, tzinfo=timezone.utc)


def test_dto_to_signal_treats_none_confidence_as_default():
    payload = {
        "symbol": "ETHUSD",
        "action": "sell",
        "confidence": None,
        "timestamp": "2024-05-10T12:00:00Z",
    }

    signal = dto_to_signal(payload)

    assert signal.confidence == 0.0
