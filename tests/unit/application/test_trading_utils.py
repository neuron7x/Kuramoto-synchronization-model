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

