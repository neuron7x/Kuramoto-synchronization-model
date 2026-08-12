# mypy: disable-error-code="unused-ignore"
"""Kafka producer for CoherenceBridge signals.

OTP (Askar's platform) uses Kafka as its distributed event log for
orders/executions. This producer publishes RegimeSignal events to
a Kafka topic so OTP's strategy framework can consume them natively
alongside order flow events.

Topic: coherence.signals.v1
Key: instrument (e.g. "EURUSD") — ensures per-instrument ordering
Value: Protobuf-serialized RegimeSignal (same wire format as gRPC)
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

logger = logging.getLogger("coherence_bridge.kafka")


def _load_pb() -> Any:
    from coherence_bridge.generated import coherence_bridge_pb2

    return coherence_bridge_pb2


def _regime_map(pb: Any) -> dict[str, int]:
    return {
        "UNKNOWN": pb.REGIME_UNKNOWN,
        "COHERENT": pb.REGIME_COHERENT,
        "METASTABLE": pb.REGIME_METASTABLE,
        "DECOHERENT": pb.REGIME_DECOHERENT,
        "CRITICAL": pb.REGIME_CRITICAL,
    }


class KafkaSignalProducer:
    """Publishes RegimeSignal dicts to Kafka as Protobuf bytes."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "coherence.signals.v1",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )
        self.topic = topic
        self._producer: Any = None
        self._pb = _load_pb()
        self._regime_map = _regime_map(self._pb)

    def _ensure_producer(self) -> None:
        if self._producer is not None:
            return
        try:
            from kafka import KafkaProducer  # type: ignore[import-not-found]

            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                key_serializer=lambda k: k.encode("utf-8"),
                value_serializer=lambda v: v,
                acks="all",
                retries=3,
                linger_ms=5,
                batch_size=16384,
            )
            logger.info("Kafka producer connected to %s", self.bootstrap_servers)
        except ImportError:
            logger.warning(
                "kafka-python not installed — Kafka output disabled. pip install kafka-python",
            )
            self._producer = None
        except Exception as exc:
            logger.warning("Kafka connection failed: %s", exc)
            self._producer = None

    def publish(self, signal: dict[str, object]) -> bool:
        """Publish a single signal. Returns True if sent, False if skipped."""
        self._ensure_producer()
        if self._producer is None:
            return False

        proto = self._pb.RegimeSignal(
            timestamp_ns=int(cast("int | float", signal["timestamp_ns"])),
            instrument=str(signal["instrument"]),
            gamma=float(cast("int | float", signal["gamma"])),
            order_parameter_R=float(cast("int | float", signal["order_parameter_R"])),
            ricci_curvature=float(cast("int | float", signal["ricci_curvature"])),
            lyapunov_max=float(cast("int | float", signal["lyapunov_max"])),
            regime=self._regime_map.get(
                str(signal.get("regime", "UNKNOWN")),
                self._regime_map["UNKNOWN"],
            ),
            regime_confidence=float(cast("int | float", signal.get("regime_confidence", 0.0))),
            regime_duration_s=float(cast("int | float", signal.get("regime_duration_s", 0.0))),
            signal_strength=float(cast("int | float", signal.get("signal_strength", 0.0))),
            risk_scalar=float(cast("int | float", signal.get("risk_scalar", 0.0))),
            sequence_number=int(cast("int | float", signal.get("sequence_number", 0))),
        )

        self._producer.send(
            self.topic,
            key=str(signal["instrument"]),
            value=proto.SerializeToString(),
        )
        return True

    def flush(self) -> None:
        if self._producer is not None:
            self._producer.flush()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()
            self._producer = None
