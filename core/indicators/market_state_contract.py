# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bounded market-state compiler contract for Kuramoto/Ricci descriptors.

The functions in this module turn the existing ``CompositeSignal`` runtime
object into a strict, auditable structural-state envelope.  The envelope is a
research descriptor contract, not financial advice and not a profitability
claim.  It records *structure* (synchronization, curvature, bounded regime
labels); it does not forecast prices, recommend positions, or assert edge.

Provenance / evidence firewall
------------------------------
Every compiled envelope carries an additive, descriptor-only
:class:`ProvenanceMetadata` block.  That block names the structural methods
and source descriptors that fed the envelope, counts the bounded inputs, and
declares an explicit claim boundary
(``claim_boundary="descriptor_only_not_predictor"``).  The metadata is
additive provenance only: it changes no runtime math and asserts no
predictive capability.  These fields exist precisely so a downstream reader
cannot mistake a structural descriptor for a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np

from .kuramoto_ricci_composite import CompositeSignal, MarketPhase

PHASE_BOUNDS = (-np.pi, np.pi)
PROBABILITY_BOUNDS = (0.0, 1.0)
RISK_MULTIPLIER_BOUNDS = (0.1, 2.0)

# --- Provenance / evidence firewall (descriptor-only metadata) -------------
# Deterministic descriptor names for the structural methods that compile an
# envelope. These are provenance labels, not capability claims.
PROVENANCE_METHOD_DESCRIPTORS: tuple[str, ...] = (
    "bounded_phase_angle",
    "classify_regime",
    "classify_entry",
    "normalize_risk",
    "build_evidence",
)
# Deterministic descriptor names for the ``CompositeSignal`` source fields
# consumed when compiling an envelope (structural inputs only).
PROVENANCE_SOURCE_DESCRIPTORS: tuple[str, ...] = (
    "kuramoto_R",
    "consensus_R",
    "cross_scale_coherence",
    "static_ricci",
    "temporal_ricci",
    "topological_transition",
    "entry_signal",
    "exit_signal",
    "risk_multiplier",
    "confidence",
)
# Frozen claim-boundary declaration applied to every compiled envelope. The
# wording is fixed so the boundary cannot drift per-call.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"


class MarketRegime(Enum):
    """Deterministic finite-state regime classifier values."""

    TREND = "TREND"
    MEAN_REVERT = "MEAN_REVERT"
    CHAOTIC = "CHAOTIC"
    TRANSITION = "TRANSITION"
    NEUTRAL = "NEUTRAL"


class EntryState(Enum):
    """Enum-based bounded entry state, not an instruction to trade."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class ProvenanceMetadata:
    """Additive, descriptor-only provenance / evidence block.

    Records which structural methods and source descriptors fed an envelope,
    how many bounded inputs were consumed, and an explicit claim boundary.
    This block makes no predictive claim: the fields are provenance labels
    and firewall declarations, never an assertion of forecast capability.
    """

    method_descriptors: tuple[str, ...]
    source_descriptors: tuple[str, ...]
    method_count: int
    source_count: int
    claim_boundary: str
    not_predictive_claim: bool
    not_financial_advice: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_descriptors": list(self.method_descriptors),
            "source_descriptors": list(self.source_descriptors),
            "method_count": self.method_count,
            "source_count": self.source_count,
            "claim_boundary": self.claim_boundary,
            "not_predictive_claim": self.not_predictive_claim,
            "not_financial_advice": self.not_financial_advice,
        }


def build_provenance() -> ProvenanceMetadata:
    """Return the deterministic descriptor-only provenance block.

    The block is identical for every envelope (descriptor labels are fixed at
    module scope) and asserts no predictive capability.
    """

    return ProvenanceMetadata(
        method_descriptors=PROVENANCE_METHOD_DESCRIPTORS,
        source_descriptors=PROVENANCE_SOURCE_DESCRIPTORS,
        method_count=len(PROVENANCE_METHOD_DESCRIPTORS),
        source_count=len(PROVENANCE_SOURCE_DESCRIPTORS),
        claim_boundary=CLAIM_BOUNDARY,
        not_predictive_claim=True,
        not_financial_advice=True,
    )


@dataclass(frozen=True, slots=True)
class MarketStateContract:
    """Strict structural-state envelope compiled from ``CompositeSignal``.

    The envelope is a bounded structural descriptor, not a forecast and not a
    recommendation. The additive ``provenance`` field records descriptor-only
    method/source metadata and the fixed claim boundary.
    """

    phase: float
    confidence: float
    regime: MarketRegime
    entry: EntryState
    exit: bool
    risk: float
    evidence: Mapping[str, Mapping[str, Any]]
    provenance: ProvenanceMetadata = field(default_factory=build_provenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "confidence": self.confidence,
            "regime": self.regime.value,
            "entry": self.entry.value,
            "exit": self.exit,
            "risk": self.risk,
            "evidence": {key: dict(value) for key, value in self.evidence.items()},
            "provenance": self.provenance.to_dict(),
        }


def _finite(value: float, fallback: float = 0.0) -> float:
    candidate = float(value)
    if np.isfinite(candidate):
        return candidate
    return fallback


def _clip(value: float, lower: float, upper: float) -> float:
    return float(np.clip(_finite(value), lower, upper))


def _clip01(value: float) -> float:
    return _clip(value, *PROBABILITY_BOUNDS)


def bounded_phase_angle(signal: CompositeSignal) -> float:
    """Encode synchronization and curvature as a bounded phase coordinate."""

    r_component = 2.0 * _clip01(signal.consensus_R) - 1.0
    ricci_component = float(np.tanh(_finite(signal.temporal_ricci)))
    return _clip(np.pi * 0.5 * (r_component + ricci_component), *PHASE_BOUNDS)


def classify_regime(signal: CompositeSignal) -> MarketRegime:
    """Map legacy phase labels to the five-state market-regime contract."""

    if signal.phase == MarketPhase.TRANSITION:
        return MarketRegime.TRANSITION
    if signal.phase in (MarketPhase.STRONG_EMERGENT, MarketPhase.PROTO_EMERGENT):
        return MarketRegime.TREND
    if signal.phase == MarketPhase.POST_EMERGENT:
        return MarketRegime.MEAN_REVERT
    if _clip01(signal.consensus_R) < 0.4 and _clip01(signal.cross_scale_coherence) < 0.6:
        return MarketRegime.NEUTRAL
    return MarketRegime.CHAOTIC


def classify_entry(signal: CompositeSignal, regime: MarketRegime) -> EntryState:
    """Derive enum entry state from bounded legacy signal fields."""

    confidence = _clip01(signal.confidence)
    entry_signal = _clip(signal.entry_signal, -1.0, 1.0)
    if confidence < 0.5:
        return EntryState.FLAT
    if regime == MarketRegime.TRANSITION:
        return EntryState.HOLD
    if regime in (MarketRegime.CHAOTIC, MarketRegime.NEUTRAL):
        return EntryState.FLAT
    if entry_signal > 0.0:
        return EntryState.LONG
    if entry_signal < 0.0:
        return EntryState.SHORT
    return EntryState.FLAT


def normalize_risk(signal: CompositeSignal) -> float:
    """Normalize legacy risk multiplier and transition pressure into [0, 1]."""

    low, high = RISK_MULTIPLIER_BOUNDS
    multiplier = _clip(signal.risk_multiplier, low, high)
    scaled_multiplier = (multiplier - low) / (high - low)
    transition = _clip01(signal.topological_transition)
    return _clip01(0.75 * scaled_multiplier + 0.25 * transition)


def build_evidence(
    signal: CompositeSignal, regime: MarketRegime, entry: EntryState
) -> dict[str, dict[str, Any]]:
    """Return separated Kuramoto, Ricci, fusion, and classification evidence."""

    risk = normalize_risk(signal)
    confidence = _clip01(signal.confidence)
    return {
        "kuramoto": {
            "kuramoto_R": _clip01(signal.kuramoto_R),
            "consensus_R": _clip01(signal.consensus_R),
            "cross_scale_coherence": _clip01(signal.cross_scale_coherence),
            "dominant_timeframe_sec": signal.dominant_timeframe_sec,
            "skipped_timeframes": list(signal.skipped_timeframes),
        },
        "ricci": {
            "static_ricci": _finite(signal.static_ricci),
            "temporal_ricci": _finite(signal.temporal_ricci),
            "topological_transition": _clip01(signal.topological_transition),
        },
        "fusion": {
            "confidence": confidence,
            "entry_signal": _clip(signal.entry_signal, -1.0, 1.0),
            "exit_signal": _clip01(signal.exit_signal),
            "risk_multiplier": _clip(signal.risk_multiplier, *RISK_MULTIPLIER_BOUNDS),
            "risk_normalized": risk,
        },
        "classification": {
            "legacy_phase": signal.phase.value,
            "regime": regime.value,
            "entry": entry.value,
            "exit": bool(_clip01(signal.exit_signal) >= 0.5),
            "deterministic": True,
            "not_financial_advice": True,
        },
    }


def compile_market_state(signal: CompositeSignal) -> MarketStateContract:
    """Compile a ``CompositeSignal`` into a strict bounded market-state object."""

    regime = classify_regime(signal)
    entry = classify_entry(signal, regime)
    evidence = build_evidence(signal, regime, entry)
    return MarketStateContract(
        phase=bounded_phase_angle(signal),
        confidence=_clip01(signal.confidence),
        regime=regime,
        entry=entry,
        exit=bool(_clip01(signal.exit_signal) >= 0.5),
        risk=normalize_risk(signal),
        evidence=evidence,
        provenance=build_provenance(),
    )


__all__ = [
    "CLAIM_BOUNDARY",
    "PROVENANCE_METHOD_DESCRIPTORS",
    "PROVENANCE_SOURCE_DESCRIPTORS",
    "EntryState",
    "MarketRegime",
    "MarketStateContract",
    "ProvenanceMetadata",
    "bounded_phase_angle",
    "build_evidence",
    "build_provenance",
    "classify_entry",
    "classify_regime",
    "compile_market_state",
    "normalize_risk",
]
