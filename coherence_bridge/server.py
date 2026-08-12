"""gRPC server for CoherenceBridge signal streaming."""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent import futures
from typing import TYPE_CHECKING, Any, cast

import grpc

from coherence_bridge.risk import compute_risk_scalar

if TYPE_CHECKING:
    from collections.abc import Generator

    from coherence_bridge.engine_interface import SignalEngine
    from coherence_bridge.kafka_producer import KafkaSignalProducer
    from coherence_bridge.questdb_writer import QuestDBSignalWriter

logger = logging.getLogger("coherence_bridge.server")


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


def _to_int(val: object) -> int:
    """Safe cast to int for dict[str, object] values."""
    return int(cast("int | float", val))


def _to_float(val: object) -> float:
    """Safe cast to float for dict[str, object] values."""
    return float(cast("int | float", val))


class CoherenceBridgeServicer:
    """Streams RegimeSignal from a SignalEngine to gRPC clients.

    Method names are PascalCase per gRPC service contract.
    """

    def __init__(
        self,
        engine: SignalEngine,
        questdb_writer: QuestDBSignalWriter,
        kafka_producer: KafkaSignalProducer | None = None,
    ) -> None:
        self.engine = engine
        self.writer = questdb_writer
        self.kafka = kafka_producer
        self._pb = _load_pb()
        self._regime_map = _regime_map(self._pb)
        self._start_time = time.time()
        self._signals_emitted = 0
        self._last_signal_ts: dict[str, int] = {}
        self._lock = threading.Lock()

    def StreamSignals(
        self,
        request: Any,
        context: grpc.ServicerContext,
    ) -> Generator[Any, None, None]:
        instruments = list(request.instruments) or self.engine.instruments
        interval_s = max(int(request.min_interval_ms), 100) / 1000.0

        logger.info(
            "StreamSignals started: instruments=%s interval_ms=%d",
            instruments,
            request.min_interval_ms,
        )

        while context.is_active():
            for inst in instruments:
                try:
                    sig = self.engine.get_signal(inst)
                    if sig is None:
                        continue
                    sig = _sanitize_signal(sig)

                    yield self._dict_to_proto(sig)

                    try:
                        self.writer.write_signal(sig)
                    except Exception as exc:
                        logger.warning("QuestDB write failed: %s", exc)

                    if self.kafka is not None:
                        try:
                            self.kafka.publish(sig)
                        except Exception as exc:
                            logger.warning("Kafka publish failed: %s", exc)

                    with self._lock:
                        self._signals_emitted += 1
                        self._last_signal_ts[inst] = _to_int(sig["timestamp_ns"])

                except Exception as exc:
                    logger.error("Signal error for %s: %s", inst, exc)

            time.sleep(interval_s)

    def GetSnapshot(
        self,
        request: Any,
        context: grpc.ServicerContext,
    ) -> Any:
        sig = self.engine.get_signal(request.instrument)
        if sig is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"No signal for {request.instrument}",
            )
            return None
        return self._dict_to_proto(_sanitize_signal(sig))

    def Health(
        self,
        request: Any,
        context: grpc.ServicerContext,
    ) -> Any:
        with self._lock:
            return self._pb.HealthResponse(
                healthy=True,
                uptime_s=int(time.time() - self._start_time),
                signals_emitted=self._signals_emitted,
                last_signal_ts=dict(self._last_signal_ts),
            )

    def _dict_to_proto(self, sig: dict[str, object]) -> Any:
        return self._pb.RegimeSignal(
            timestamp_ns=_to_int(sig["timestamp_ns"]),
            instrument=str(sig["instrument"]),
            gamma=_to_float(sig["gamma"]),
            order_parameter_R=_to_float(sig["order_parameter_R"]),
            ricci_curvature=_to_float(sig["ricci_curvature"]),
            lyapunov_max=_to_float(sig["lyapunov_max"]),
            regime=self._regime_map.get(
                str(sig.get("regime", "UNKNOWN")),
                self._regime_map["UNKNOWN"],
            ),
            regime_confidence=_to_float(sig.get("regime_confidence", 0.0)),
            regime_duration_s=_to_float(sig.get("regime_duration_s", 0.0)),
            signal_strength=_to_float(sig.get("signal_strength", 0.0)),
            risk_scalar=_to_float(sig.get("risk_scalar", 0.0)),
            sequence_number=_to_int(sig.get("sequence_number", 0)),
        )


def _sanitize_signal(sig: dict[str, object]) -> dict[str, object]:
    """Fail-closed: non-finite gamma forces risk_scalar=0 and regime=UNKNOWN."""
    out = dict(sig)
    gamma = _to_float(out.get("gamma", float("nan")))
    if not math.isfinite(gamma):
        out["risk_scalar"] = 0.0
        out["regime"] = "UNKNOWN"
    else:
        out.setdefault("risk_scalar", compute_risk_scalar(gamma, fail_closed=True))
    return out


def serve(
    engine: SignalEngine,
    host: str = "0.0.0.0",
    port: int = 50051,
    questdb_host: str = "localhost",
    questdb_port: int = 9000,
    kafka_bootstrap: str | None = None,
) -> None:
    """Start the gRPC server (blocking)."""
    from coherence_bridge.generated import coherence_bridge_pb2_grpc as pb_grpc
    from coherence_bridge.kafka_producer import KafkaSignalProducer
    from coherence_bridge.questdb_writer import QuestDBSignalWriter

    writer = QuestDBSignalWriter(host=questdb_host, port=questdb_port)
    kafka = KafkaSignalProducer(bootstrap_servers=kafka_bootstrap) if kafka_bootstrap else None
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.http2.min_ping_interval_without_data_ms", 5000),
        ],
    )
    servicer = CoherenceBridgeServicer(engine, writer, kafka)
    pb_grpc.add_CoherenceBridgeServicer_to_server(servicer, server)  # type: ignore[no-untyped-call]
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    logger.info("CoherenceBridge gRPC server on %s:%d", host, port)
    server.wait_for_termination()
