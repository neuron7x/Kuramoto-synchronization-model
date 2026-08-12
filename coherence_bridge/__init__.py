"""CoherenceBridge — GeoSync → OTS regime signal transport.

Public API::

    from coherence_bridge import RegimeSignal, Regime, SignalEngine
    from coherence_bridge import MockEngine, CoherenceRiskGate
    from coherence_bridge import verify_signal, compute_risk_scalar

Architecture layers (top → bottom):

    ┌─────────────────────────────────────────────┐
    │  Transport    gRPC · Kafka · HTTP/SSE       │
    ├─────────────────────────────────────────────┤
    │  Verification invariants · metrics          │
    ├─────────────────────────────────────────────┤
    │  Gate         risk_gate · feature_exporter  │
    ├─────────────────────────────────────────────┤
    │  Engine       geosync_adapter · mock_engine │
    ├─────────────────────────────────────────────┤
    │  Contract     signal · risk · Regime enum   │
    └─────────────────────────────────────────────┘
"""

from coherence_bridge.invariants import InvariantViolation, verify_signal
from coherence_bridge.risk import compute_risk_scalar
from coherence_bridge.signal import Regime, RegimeSignal

__all__ = [
    "Regime",
    "RegimeSignal",
    "InvariantViolation",
    "verify_signal",
    "compute_risk_scalar",
]
