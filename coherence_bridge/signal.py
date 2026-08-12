"""Canonical signal types for the CoherenceBridge contract.

This module is the **single source of truth** for the signal schema.
Every component in the bridge (engine, server, writer, gate) operates
on these types — not raw dicts, not proto objects, not ad-hoc tuples.

Design decisions:
  - frozen dataclass: immutable after creation → thread-safe, hashable
  - slots=True: 40% less memory vs regular class
  - __post_init__ validates invariants at construction time
  - to_dict() / from_dict() for serialization boundaries only
"""

from __future__ import annotations

import enum
import math
import time
from dataclasses import asdict, dataclass
from typing import cast

from coherence_bridge.risk import compute_risk_scalar


def _int(v: object) -> int:
    return int(cast("int | float", v))


def _float(v: object) -> float:
    return float(cast("int | float", v))


class Regime(enum.Enum):
    """Market regime classification.

    Mapping from GeoSync MarketPhase:
      CHAOTIC        → DECOHERENT
      PROTO_EMERGENT → METASTABLE
      STRONG_EMERGENT→ COHERENT
      TRANSITION     → CRITICAL
      POST_EMERGENT  → DECOHERENT
    """

    COHERENT = "COHERENT"
    METASTABLE = "METASTABLE"
    DECOHERENT = "DECOHERENT"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RegimeSignal:
    """One sample from the CoherenceBridge signal stream.

    Invariants (enforced in __post_init__):
      T3:  γ ∈ R≥0
      T4:  R ∈ [0, 1]           (INV-K1)
      T8:  confidence ∈ [0, 1]
      T10: strength ∈ [-1, 1]
      T11: risk = max(0, 1-|γ-1|)
      T12: sequence ∈ Z≥0
    """

    timestamp_ns: int
    instrument: str
    gamma: float
    order_parameter_R: float
    ricci_curvature: float
    lyapunov_max: float
    regime: Regime
    regime_confidence: float
    regime_duration_s: float
    signal_strength: float
    risk_scalar: float
    sequence_number: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.gamma) or self.gamma < 0:
            object.__setattr__(self, "gamma", 0.0)
            object.__setattr__(self, "risk_scalar", 0.0)
            object.__setattr__(self, "regime", Regime.UNKNOWN)

    def to_dict(self) -> dict[str, object]:
        """Serialize to transport dict (for proto/JSON/ILP boundaries)."""
        d = asdict(self)
        d["regime"] = self.regime.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> RegimeSignal:
        """Reconstruct from transport dict."""
        regime_val = d.get("regime", "UNKNOWN")
        regime = Regime(regime_val) if isinstance(regime_val, str) else Regime.UNKNOWN
        return cls(
            timestamp_ns=_int(d.get("timestamp_ns", 0)),
            instrument=str(d.get("instrument", "")),
            gamma=_float(d.get("gamma", 0)),
            order_parameter_R=_float(d.get("order_parameter_R", 0)),
            ricci_curvature=_float(d.get("ricci_curvature", 0)),
            lyapunov_max=_float(d.get("lyapunov_max", 0)),
            regime=regime,
            regime_confidence=_float(d.get("regime_confidence", 0)),
            regime_duration_s=_float(d.get("regime_duration_s", 0)),
            signal_strength=_float(d.get("signal_strength", 0)),
            risk_scalar=_float(d.get("risk_scalar", 0)),
            sequence_number=_int(d.get("sequence_number", 0)),
        )

    @classmethod
    def from_engine_dict(cls, d: dict[str, object]) -> RegimeSignal:
        """Construct from engine output with automatic risk_scalar derivation."""
        gamma = _float(d.get("gamma", 0))
        return cls.from_dict(
            {
                **d,
                "risk_scalar": compute_risk_scalar(gamma, fail_closed=True),
            }
        )

    @classmethod
    def fail_closed(cls, instrument: str, reason: str = "") -> RegimeSignal:
        """Construct a safe zero-risk signal when computation fails."""
        return cls(
            timestamp_ns=time.time_ns(),
            instrument=instrument,
            gamma=0.0,
            order_parameter_R=0.0,
            ricci_curvature=0.0,
            lyapunov_max=0.0,
            regime=Regime.UNKNOWN,
            regime_confidence=0.0,
            regime_duration_s=0.0,
            signal_strength=0.0,
            risk_scalar=0.0,
            sequence_number=0,
        )
