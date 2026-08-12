"""Kafka producer tests (unit-level, no running Kafka required)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from coherence_bridge.kafka_producer import KafkaSignalProducer


def _make_signal(**overrides) -> dict:
    base = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.001,
        "regime": "METASTABLE",
        "regime_confidence": 0.8,
        "regime_duration_s": 10.0,
        "signal_strength": 0.1,
        "risk_scalar": 0.9,
        "sequence_number": 0,
    }
    base.update(overrides)
    return base


@patch("coherence_bridge.kafka_producer.KafkaSignalProducer._ensure_producer")
def test_publish_serializes_protobuf(mock_ensure):
    producer = KafkaSignalProducer()
    producer._producer = MagicMock()

    sig = _make_signal()
    result = producer.publish(sig)

    assert result is True
    producer._producer.send.assert_called_once()
    call_args = producer._producer.send.call_args
    assert call_args[0][0] == "coherence.signals.v1"
    assert call_args[1]["key"] == "EURUSD"
    # Value should be bytes (protobuf serialized)
    assert isinstance(call_args[1]["value"], bytes)


@patch("coherence_bridge.kafka_producer.KafkaSignalProducer._ensure_producer")
def test_publish_returns_false_when_no_producer(mock_ensure):
    producer = KafkaSignalProducer()
    producer._producer = None

    sig = _make_signal()
    result = producer.publish(sig)

    assert result is False


@patch("coherence_bridge.kafka_producer.KafkaSignalProducer._ensure_producer")
def test_protobuf_roundtrip_through_kafka_value(mock_ensure):
    """Verify the protobuf bytes can be deserialized back."""
    from coherence_bridge.generated import coherence_bridge_pb2 as pb

    producer = KafkaSignalProducer()
    producer._producer = MagicMock()

    sig = _make_signal(gamma=1.05, instrument="GBPUSD", regime="CRITICAL")
    producer.publish(sig)

    sent_bytes = producer._producer.send.call_args[1]["value"]
    restored = pb.RegimeSignal()
    restored.ParseFromString(sent_bytes)

    assert restored.instrument == "GBPUSD"
    assert abs(restored.gamma - 1.05) < 1e-10
    assert restored.regime == pb.REGIME_CRITICAL


def test_default_topic() -> None:
    producer = KafkaSignalProducer()
    assert producer.topic == "coherence.signals.v1"


def test_custom_config() -> None:
    producer = KafkaSignalProducer(
        bootstrap_servers="kafka.prod:9092",
        topic="custom.topic",
    )
    assert producer.bootstrap_servers == "kafka.prod:9092"
    assert producer.topic == "custom.topic"
