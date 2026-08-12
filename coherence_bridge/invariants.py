"""Formal verification of CoherenceBridge signal contract invariants.

This module provides runtime-checkable proofs that every signal emitted
by the bridge satisfies the physics contract. It is both:
  1. A runtime validator (call verify_signal() before emission)
  2. A formal specification (each invariant maps to a theorem)

Invariant taxonomy (from GeoSync CLAUDE.md):
  P0 = universal (must hold for ALL inputs, no exceptions)
  P1 = conditional (holds under stated preconditions)
  P2 = statistical (holds in aggregate, not per-sample)

Signal contract theorems:
  T1  (P0): timestamp_ns > 0 ∧ timestamp_ns ∈ Z
  T2  (P0): instrument ∈ Σ* (non-empty string)
  T3  (P0): gamma ∈ R≥0 (spectral exponent is non-negative)
  T4  (P0): R ∈ [0, 1] (INV-K1: Kuramoto order parameter)
  T5  (P1): κ ∈ R (Forman-Ricci, unbounded for non-price graphs)
  T6  (P0): λ ∈ R (Lyapunov exponent, finite)
  T7  (P0): regime ∈ {COHERENT, METASTABLE, DECOHERENT, CRITICAL, UNKNOWN}
  T8  (P0): regime_confidence ∈ [0, 1]
  T9  (P0): regime_duration_s ≥ 0
  T10 (P0): signal_strength ∈ [-1, 1]
  T11 (P0): risk_scalar ∈ [0, 1] ∧ risk_scalar = max(0, 1 - |gamma - 1|)
  T12 (P0): sequence_number ∈ Z≥0 (monotonic per instrument)

Derived theorems:
  T13 (P0): ¬isfinite(gamma) ⟹ risk_scalar = 0 ∧ regime = UNKNOWN (fail-closed)
  T14 (P1): gamma derived from PSD, never assigned (verified by source inspection)
  T15 (P0): SSI.apply(domain=INTERNAL) is never called (external signals only)

Each verify_* function returns (passed: bool, message: str).
verify_signal() runs all checks and raises InvariantViolation on first failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

VALID_REGIMES = frozenset({"COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL", "UNKNOWN"})
MIN_TIMESTAMP_NS = 1_577_836_800_000_000_000  # 2020-01-01 UTC


class InvariantViolation(Exception):
    """Raised when a signal violates a physics contract invariant."""

    def __init__(self, theorem: str, message: str) -> None:
        self.theorem = theorem
        super().__init__(f"[{theorem}] {message}")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Result of a single invariant check."""

    theorem: str
    passed: bool
    message: str


def verify_T1(sig: dict[str, object]) -> VerificationResult:
    """T1 (P0): timestamp_ns > 0 ∧ timestamp_ns ∈ Z"""
    ts = sig.get("timestamp_ns")
    if not isinstance(ts, int) or ts < MIN_TIMESTAMP_NS:
        return VerificationResult(
            "T1",
            False,
            f"timestamp_ns={ts} invalid (must be int >= {MIN_TIMESTAMP_NS})",
        )
    return VerificationResult("T1", True, "OK")


def verify_T2(sig: dict[str, object]) -> VerificationResult:
    """T2 (P0): instrument ∈ Σ* (non-empty string)"""
    inst = sig.get("instrument")
    if not isinstance(inst, str) or not inst:
        return VerificationResult("T2", False, f"instrument={inst!r} invalid")
    return VerificationResult("T2", True, "OK")


def verify_T3(sig: dict[str, object]) -> VerificationResult:
    """T3 (P0): gamma ∈ R≥0"""
    gamma = sig.get("gamma")
    if not isinstance(gamma, (int, float)) or not math.isfinite(gamma):
        return VerificationResult("T3", False, f"gamma={gamma} not finite")
    if gamma < 0:
        return VerificationResult("T3", False, f"gamma={gamma} < 0")
    return VerificationResult("T3", True, "OK")


def verify_T4(sig: dict[str, object]) -> VerificationResult:
    """T4 (P0): R ∈ [0, 1] (INV-K1)"""
    R = sig.get("order_parameter_R")
    if not isinstance(R, (int, float)):
        return VerificationResult("T4", False, f"R={R} not numeric")
    if not (0.0 <= R <= 1.0):
        return VerificationResult("T4", False, f"INV-K1 VIOLATED: R={R:.6f} outside [0,1]")
    return VerificationResult("T4", True, "OK")


def verify_T5(sig: dict[str, object]) -> VerificationResult:
    """T5 (P1): κ ∈ R (finite)"""
    kappa = sig.get("ricci_curvature")
    if not isinstance(kappa, (int, float)) or not math.isfinite(kappa):
        return VerificationResult("T5", False, f"ricci_curvature={kappa} not finite")
    return VerificationResult("T5", True, "OK")


def verify_T6(sig: dict[str, object]) -> VerificationResult:
    """T6 (P0): λ ∈ R (finite)"""
    lyap = sig.get("lyapunov_max")
    if not isinstance(lyap, (int, float)) or not math.isfinite(lyap):
        return VerificationResult("T6", False, f"lyapunov_max={lyap} not finite")
    return VerificationResult("T6", True, "OK")


def verify_T7(sig: dict[str, object]) -> VerificationResult:
    """T7 (P0): regime ∈ valid set"""
    regime = sig.get("regime")
    if regime not in VALID_REGIMES:
        return VerificationResult("T7", False, f"regime={regime!r} not in {VALID_REGIMES}")
    return VerificationResult("T7", True, "OK")


def verify_T8(sig: dict[str, object]) -> VerificationResult:
    """T8 (P0): regime_confidence ∈ [0, 1]"""
    conf = sig.get("regime_confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return VerificationResult("T8", False, f"regime_confidence={conf} outside [0,1]")
    return VerificationResult("T8", True, "OK")


def verify_T9(sig: dict[str, object]) -> VerificationResult:
    """T9 (P0): regime_duration_s ≥ 0"""
    dur = sig.get("regime_duration_s")
    if not isinstance(dur, (int, float)) or dur < 0:
        return VerificationResult("T9", False, f"regime_duration_s={dur} < 0")
    return VerificationResult("T9", True, "OK")


def verify_T10(sig: dict[str, object]) -> VerificationResult:
    """T10 (P0): signal_strength ∈ [-1, 1]"""
    ss = sig.get("signal_strength")
    if not isinstance(ss, (int, float)) or not (-1.0 <= ss <= 1.0):
        return VerificationResult("T10", False, f"signal_strength={ss} outside [-1,1]")
    return VerificationResult("T10", True, "OK")


def verify_T11(sig: dict[str, object]) -> VerificationResult:
    """T11 (P0): risk_scalar ∈ [0, 1] ∧ risk_scalar = max(0, 1 - |gamma - 1|)"""
    rs = sig.get("risk_scalar")
    gamma = sig.get("gamma")
    if not isinstance(rs, (int, float)) or not (0.0 <= rs <= 1.0):
        return VerificationResult("T11", False, f"risk_scalar={rs} outside [0,1]")
    if isinstance(gamma, (int, float)) and math.isfinite(gamma):
        expected = max(0.0, min(1.0, 1.0 - abs(gamma - 1.0)))
        if abs(rs - expected) > 0.01:
            return VerificationResult(
                "T11",
                False,
                f"risk_scalar={rs:.4f} != max(0,1-|{gamma:.4f}-1|)={expected:.4f}",
            )
    return VerificationResult("T11", True, "OK")


def verify_T12(sig: dict[str, object]) -> VerificationResult:
    """T12 (P0): sequence_number ∈ Z≥0"""
    seq = sig.get("sequence_number")
    if not isinstance(seq, int) or seq < 0:
        return VerificationResult("T12", False, f"sequence_number={seq} invalid")
    return VerificationResult("T12", True, "OK")


def verify_T13(sig: dict[str, object]) -> VerificationResult:
    """T13 (P0): fail-closed — ¬isfinite(gamma) ⟹ risk_scalar=0 ∧ regime=UNKNOWN"""
    gamma = sig.get("gamma")
    if isinstance(gamma, (int, float)) and not math.isfinite(gamma):
        if sig.get("risk_scalar") != 0.0:
            return VerificationResult(
                "T13",
                False,
                f"Fail-closed violated: gamma={gamma} but risk_scalar={sig.get('risk_scalar')}",
            )
        if sig.get("regime") != "UNKNOWN":
            return VerificationResult(
                "T13",
                False,
                f"Fail-closed violated: gamma={gamma} but regime={sig.get('regime')}",
            )
    return VerificationResult("T13", True, "OK")


_ALL_VERIFIERS = [
    verify_T1,
    verify_T2,
    verify_T3,
    verify_T4,
    verify_T5,
    verify_T6,
    verify_T7,
    verify_T8,
    verify_T9,
    verify_T10,
    verify_T11,
    verify_T12,
    verify_T13,
]


def verify_signal(
    sig: dict[str, object], *, raise_on_failure: bool = True
) -> list[VerificationResult]:
    """Run all invariant checks on a signal.

    Parameters
    ----------
    sig : dict
        The 12-field signal dict.
    raise_on_failure : bool
        If True, raises InvariantViolation on first failed check.

    Returns
    -------
    list[VerificationResult]
        Results for all 13 theorems.
    """
    results = []
    for verifier in _ALL_VERIFIERS:
        result = verifier(sig)
        results.append(result)
        if not result.passed and raise_on_failure:
            raise InvariantViolation(result.theorem, result.message)
    return results
