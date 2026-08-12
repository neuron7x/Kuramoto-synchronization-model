# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed physics-contract gate for the CoherenceBridge → risk layer.

The bridge adapter (``coherence_bridge.geosync_adapter``) is advisory and
read-only: it relays GeoSync physics-kernel outputs verbatim. That faithfulness
created a documented OPEN GAP (ledger ``coherence-bridge-geosync-adapter``):

  1. The adapter relays an out-of-band NEGATIVE gamma straight to the risk
     layer with no fail-closed status — gamma is a spectral exponent and is
     only physically meaningful on ``gamma ≥ 0`` (bridge theorem T3).
  2. The adapter's exposed ``ricci_curvature`` field is an *augmented-Forman*
     blend, which is LEGITIMATELY unbounded above (Forman curvature can exceed
     1). It was named as if it were the Ollivier κ that INV-RC1 (κ ≤ 1) governs.
     Treating a Forman value > 1 as an INV-RC1 violation is a category error;
     treating it as κ-bound "evidence" downstream is worse.

This module closes the gap WITHOUT mutating the advisory relay: it is a separate
gate the risk layer calls on a relayed signal. It distinguishes the two Ricci
notions by name and applies INV-RC1 ONLY to the Ollivier operator.

INV-CBR1 (CLAUDE.md): the bridge → risk handoff is VALID only if
    R ∈ [0, 1]                       (INV-K1)
  ∧ ollivier_kappa ≤ 1 (when present) (INV-RC1, Ollivier operator only)
  ∧ gamma finite ∧ gamma ≥ 0          (T3 accepted domain)
Otherwise status = INVALID_PHYSICS_CONTRACT, decision = NO_GO and the risk
signal is forced to the safe floor 0.0. ``augmented_forman_ricci`` is checked
for finiteness ONLY — it is never compared against the κ ≤ 1 bound, and it is
never accepted as κ-bound evidence.

NON-CLAIM: this is a contract gate, not a trading signal. VALID means "physics
contract preserved", not "trade". No alpha, no market law, synthetic-only paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from coherence_bridge.risk import compute_risk_scalar

# INV-RC1 numerical slack — identical to the canonical Ollivier-Ricci geometry
# witness; absorbs only floating-point rounding in the optimal-transport solve.
# The definitional bound is κ ≤ 1, so the admissible ceiling is 1 + eps.
CURVATURE_EPS: float = 1e-9
KAPPA_UPPER_BOUND: float = 1.0 + CURVATURE_EPS

# Safe risk floor emitted on any contract violation (fail-closed).
SAFE_RISK_FLOOR: float = 0.0


class PhysicsContractStatus(str, Enum):
    """Outcome of the bridge physics-contract gate."""

    VALID = "VALID"
    INVALID_PHYSICS_CONTRACT = "INVALID_PHYSICS_CONTRACT"


class BridgeDecision(str, Enum):
    """Decision handed to the risk layer.

    PASS  — physics contract preserved; downstream may act on the bounded risk.
    NO_GO — contract violated; fail-closed, do not act.
    """

    PASS = "PASS"
    NO_GO = "NO_GO"


@dataclass(frozen=True, slots=True)
class ContractVerdict:
    """Fail-closed verdict the risk layer consumes instead of a raw signal.

    CONTRACT FOR DOWNSTREAM: the risk layer MUST act on ``decision`` /
    ``safe_risk_scalar`` from this verdict, NOT on the relayed signal's raw
    ``risk_scalar``. The raw field is advisory telemetry and is left intact for
    observability; reading it past an INVALID_PHYSICS_CONTRACT verdict defeats
    the fail-closed design (``safe_risk_scalar`` is 0.0 on any violation).
    """

    status: PhysicsContractStatus
    decision: BridgeDecision
    safe_risk_scalar: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return self.status is PhysicsContractStatus.VALID


@dataclass(frozen=True, slots=True)
class BridgeSignal:
    """Typed parse of a relayed bridge signal at the DECISION boundary.

    The raw ``risk_scalar`` is intentionally absent from the typed decision
    surface — it lives only in ``telemetry`` (advisory), so it is impossible to
    type a raw-risk value into a sizing decision. Use :meth:`from_relayed` to
    parse a transport dict; the wire format stays a dict, the decision boundary
    is typed.
    """

    gamma: float | None
    order_parameter_R: float | None
    augmented_forman_ricci: float | None
    ollivier_kappa: float | None
    telemetry: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_relayed(cls, sig: dict[str, object]) -> "BridgeSignal":
        forman = sig.get("augmented_forman_ricci", sig.get("ricci_curvature"))
        return cls(
            gamma=_as_float(sig.get("gamma")),
            order_parameter_R=_as_float(sig.get("order_parameter_R")),
            augmented_forman_ricci=_as_float(forman),
            ollivier_kappa=(
                _as_float(sig.get("ollivier_kappa")) if "ollivier_kappa" in sig else None
            ),
            telemetry={"raw_risk_scalar": sig.get("risk_scalar"), "regime": sig.get("regime")},
        )

    def to_contract_dict(self) -> dict[str, object]:
        """The minimal field set ``validate_physics_contract`` needs (no raw risk)."""
        out: dict[str, object] = {
            "gamma": self.gamma,
            "order_parameter_R": self.order_parameter_R,
            "augmented_forman_ricci": self.augmented_forman_ricci,
        }
        if self.ollivier_kappa is not None:
            out["ollivier_kappa"] = self.ollivier_kappa
        return out


@dataclass(frozen=True, slots=True)
class ValidatedBridgeSignal:
    """A bridge signal that has passed (or failed) the contract — the ONLY type
    a sizing consumer should accept. Carries the verdict + the safe risk; there
    is no raw-risk field to misuse."""

    verdict: ContractVerdict
    safe_risk_scalar: float
    regime: str

    @classmethod
    def of(cls, signal: BridgeSignal) -> "ValidatedBridgeSignal":
        verdict = validate_physics_contract(signal.to_contract_dict())
        return cls(
            verdict=verdict,
            safe_risk_scalar=verdict.safe_risk_scalar,
            regime=str(signal.telemetry.get("regime", "UNKNOWN")),
        )


def _as_float(value: object) -> float | None:
    """Coerce to float, or None if not a real finite-capable number."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def validate_physics_contract(sig: dict[str, object]) -> ContractVerdict:
    """Gate a relayed bridge signal against INV-CBR1. Fail-closed.

    Parameters
    ----------
    sig
        A relayed signal dict. Recognised fields:
          ``order_parameter_R``      — Kuramoto R (INV-K1)
          ``gamma``                  — spectral exponent (T3 accepted domain)
          ``ollivier_kappa``         — Ollivier-Ricci κ (INV-RC1), optional
          ``augmented_forman_ricci`` — Forman blend, finite-only (may exceed 1)
        For backward compatibility, when ``augmented_forman_ricci`` is absent the
        legacy ``ricci_curvature`` field is read as the Forman blend.

    Returns
    -------
    ContractVerdict
        On any violation: INVALID_PHYSICS_CONTRACT / NO_GO / risk = 0.0.
        On full compliance: VALID / PASS / risk = bounded relayed risk_scalar.
    """
    reasons: list[str] = []

    # INV-K1 — R ∈ [0, 1].
    r = _as_float(sig.get("order_parameter_R"))
    if r is None or not math.isfinite(r) or not (0.0 <= r <= 1.0):
        reasons.append(f"INV-K1: order_parameter_R={sig.get('order_parameter_R')!r} outside [0,1]")

    # T3 — gamma finite AND in the accepted domain gamma ≥ 0. A negative
    # out-of-band gamma is the documented relay hazard: it MUST fail closed.
    gamma = _as_float(sig.get("gamma"))
    if gamma is None or not math.isfinite(gamma):
        reasons.append(f"T3: gamma={sig.get('gamma')!r} not finite")
    elif gamma < 0.0:
        reasons.append(f"T3: gamma={gamma:.6f} < 0 (out-of-band spectral exponent)")

    # INV-RC1 — Ollivier κ ≤ 1, applied ONLY to the Ollivier operator. Optional:
    # absent ⇒ not asserted (the adapter may not have computed it on a path).
    if "ollivier_kappa" in sig:
        ok = _as_float(sig.get("ollivier_kappa"))
        if ok is None or not math.isfinite(ok):
            reasons.append(f"INV-RC1: ollivier_kappa={sig.get('ollivier_kappa')!r} not finite")
        elif ok > KAPPA_UPPER_BOUND:
            reasons.append(f"INV-RC1: ollivier_kappa={ok:.9f} > {KAPPA_UPPER_BOUND:.9f}")

    # Augmented-Forman blend: finiteness ONLY. Forman curvature is legitimately
    # unbounded above, so a value > 1 is NEVER a violation here and is NEVER
    # treated as κ-bound evidence (that is what ollivier_kappa is for).
    forman_raw = sig.get("augmented_forman_ricci", sig.get("ricci_curvature"))
    if forman_raw is not None:
        forman = _as_float(forman_raw)
        if forman is None or not math.isfinite(forman):
            reasons.append(f"augmented_forman_ricci={forman_raw!r} not finite")

    if reasons:
        return ContractVerdict(
            status=PhysicsContractStatus.INVALID_PHYSICS_CONTRACT,
            decision=BridgeDecision.NO_GO,
            safe_risk_scalar=SAFE_RISK_FLOOR,
            reasons=tuple(reasons),
        )

    # Contract preserved: pass through a bounded, fail-closed risk scalar.
    assert gamma is not None  # narrowed by the checks above
    risk = compute_risk_scalar(gamma, fail_closed=True)
    return ContractVerdict(
        status=PhysicsContractStatus.VALID,
        decision=BridgeDecision.PASS,
        safe_risk_scalar=float(max(0.0, min(1.0, risk))),
        reasons=(),
    )
