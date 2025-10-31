from datetime import datetime, timezone

import pytest

from domain import ModelMetadata, Signal, SignalAction


PROVENANCE = ModelMetadata(
    model_id="test.domain.signal",
    model_version="0.0.1",
    model_hash="domain-test-model",
    training_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
)


def test_signal_validation_enforces_confidence_range() -> None:
    with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
        Signal(
            symbol="BTCUSD",
            action=SignalAction.BUY,
            confidence=1.5,
            model_metadata=PROVENANCE,
        )


def test_signal_to_dict_round_trips_metadata() -> None:
    signal = Signal(
        symbol="ETHUSD",
        action=SignalAction.SELL,
        confidence=0.7,
        model_metadata=PROVENANCE,
        rationale="overbought",
        metadata={"indicator": "rsi"},
    )
    payload = signal.to_dict()
    assert payload["symbol"] == "ETHUSD"
    assert payload["action"] == SignalAction.SELL.value
    assert payload["metadata"] == {"indicator": "rsi"}
    assert payload["model_id"] == PROVENANCE.model_id
    assert payload["model_version"] == PROVENANCE.model_version
    assert payload["model_hash"] == PROVENANCE.model_hash
    assert payload["training_timestamp"] == PROVENANCE.training_timestamp.isoformat()

    boosted = signal.with_confidence(0.9)
    assert boosted.confidence == pytest.approx(0.9)
    assert boosted.metadata == signal.metadata
    assert boosted.model_metadata is PROVENANCE


def test_signal_requires_model_metadata() -> None:
    with pytest.raises(TypeError):
        Signal(symbol="BTCUSD", action=SignalAction.BUY, confidence=0.5, model_metadata=None)  # type: ignore[arg-type]
