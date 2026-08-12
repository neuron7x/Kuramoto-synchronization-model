"""Prometheus metrics for CoherenceBridge observability.

Exposes:
  coherence_bridge_signals_total          — counter per instrument
  coherence_bridge_signal_latency_seconds — histogram of compute time
  coherence_bridge_gamma                  — gauge per instrument
  coherence_bridge_order_parameter_R      — gauge per instrument
  coherence_bridge_risk_scalar            — gauge per instrument
  coherence_bridge_regime                 — info per instrument (label)
  coherence_bridge_questdb_writes_total   — counter
  coherence_bridge_questdb_errors_total   — counter
  coherence_bridge_kafka_publishes_total  — counter
  coherence_bridge_kafka_errors_total     — counter
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# Signal emission
SIGNALS_TOTAL = Counter(
    "coherence_bridge_signals_total",
    "Total signals emitted",
    ["instrument"],
)

SIGNAL_LATENCY = Histogram(
    "coherence_bridge_signal_latency_seconds",
    "Time to compute one signal",
    ["instrument"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

# Physics gauges
GAMMA = Gauge(
    "coherence_bridge_gamma",
    "PSD spectral exponent (derived)",
    ["instrument"],
)

ORDER_PARAMETER_R = Gauge(
    "coherence_bridge_order_parameter_R",
    "Kuramoto order parameter R(t)",
    ["instrument"],
)

RISK_SCALAR = Gauge(
    "coherence_bridge_risk_scalar",
    "Position size multiplier from gamma distance",
    ["instrument"],
)

REGIME_INFO = Info(
    "coherence_bridge_regime",
    "Current regime classification",
)

# Sink counters
QUESTDB_WRITES = Counter(
    "coherence_bridge_questdb_writes_total",
    "Successful QuestDB writes",
)
QUESTDB_ERRORS = Counter(
    "coherence_bridge_questdb_errors_total",
    "Failed QuestDB writes",
)
KAFKA_PUBLISHES = Counter(
    "coherence_bridge_kafka_publishes_total",
    "Successful Kafka publishes",
)
KAFKA_ERRORS = Counter(
    "coherence_bridge_kafka_errors_total",
    "Failed Kafka publishes",
)


def record_signal(signal: dict[str, object]) -> None:
    """Update all Prometheus metrics from an emitted signal."""
    inst = str(signal.get("instrument", "unknown"))
    SIGNALS_TOTAL.labels(instrument=inst).inc()
    GAMMA.labels(instrument=inst).set(float(signal.get("gamma", 0) or 0))  # type: ignore[arg-type]
    ORDER_PARAMETER_R.labels(instrument=inst).set(float(signal.get("order_parameter_R", 0) or 0))  # type: ignore[arg-type]
    RISK_SCALAR.labels(instrument=inst).set(float(signal.get("risk_scalar", 0) or 0))  # type: ignore[arg-type]
    REGIME_INFO.info(
        {
            "instrument": inst,
            "regime": str(signal.get("regime", "UNKNOWN")),
        }
    )
