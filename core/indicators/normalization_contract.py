# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable normalization contract for claim-bearing fused-signal paths.

GeoSync fuses heterogeneous structural descriptors --- Ricci curvature,
Kuramoto synchronization, L2 / liquidity, volatility, cost / slippage, and a
baseline reference --- into a single bounded market-state envelope (see
:mod:`core.indicators.market_state_contract`). Those source descriptors live
on wildly different native scales: a Ricci curvature near zero, a Kuramoto
order parameter in ``[0, 1]``, an L2 depth in units of base-asset size, a
volatility in return-fraction units, a cost in basis points. A fused kernel
that consumes raw, un-normalized inputs is *scale dominated*: the descriptor
with the largest amplitude silently steers the structural verdict, and the
claim "the fused structure says X" becomes an artefact of unit choice rather
than of structure.

This module converts normalization from documentation into **executable
validation behaviour**. It provides:

* a typed :class:`NormalizationSpec` per signal (raw units, reference window,
  transform, fit scope, output schema, raw / transform-config / normalized
  hashes);
* a fail-closed :func:`validate_normalization` that rejects a spec with
  missing units, missing transform, future-fit leakage, inconsistent
  sampling, or a missing raw / output hash;
* a :func:`raw_scale_ablation` helper that compares a fused-kernel verdict on
  normalized inputs against its verdict on raw-scale inputs, so any fused
  claim *must* exhibit its scale sensitivity;
* an :class:`NormalizationStatus` enum and :func:`gate_claim_promotion` guard
  that refuses to promote a claim whose normalization status is
  ``NOT_RUN``, ``PARTIAL``, or ``SCALE_SENSITIVE``.

Claim boundary
--------------
This is a *normalization-integrity* contract. It asserts nothing about
predictive capability, market edge, profitability, or rank. It only enforces
that a fused structural descriptor is computed on commensurate scales and
carries auditable provenance. The fixed boundary token below makes that
explicit so a downstream reader cannot mistake scale hygiene for a forecast.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Fixed claim-boundary declaration applied to every normalization evidence
# bundle. The wording is frozen so the boundary cannot drift per-call.
NORMALIZATION_CLAIM_BOUNDARY: str = "normalization_integrity_only_not_predictor"

# Canonical heterogeneous source descriptors that feed a fused-kernel claim.
# These are the claim-bearing inputs the normalization contract governs.
CLAIM_BEARING_SIGNALS: tuple[str, ...] = (
    "returns",
    "l2_liquidity",
    "ricci_field",
    "kuramoto_phase",
    "volatility",
    "cost_state",
    "baseline",
)

# Transforms recognised by the contract. ``identity`` is the explicit
# "raw-scale, no normalization" marker used by the ablation path; it is a
# valid *declared* transform but is SCALE_SENSITIVE by construction.
KNOWN_TRANSFORMS: tuple[str, ...] = (
    "identity",
    "zscore",
    "robust_zscore",
    "minmax",
    "rank",
    "log_return",
)

# Transforms that genuinely remove scale domination. ``identity`` and
# ``minmax`` are intentionally excluded: identity preserves raw scale, and
# minmax is amplitude-sensitive to outliers / window extrema.
SCALE_INVARIANT_TRANSFORMS: frozenset[str] = frozenset({"zscore", "robust_zscore", "rank"})


class NormalizationStatus(Enum):
    """Deterministic normalization status used to gate claim promotion."""

    NORMALIZED = "NORMALIZED"
    SCALE_SENSITIVE = "SCALE_SENSITIVE"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


# Statuses that MUST block claim promotion (audit requirement 7).
BLOCKING_STATUSES: frozenset[NormalizationStatus] = frozenset(
    {
        NormalizationStatus.NOT_RUN,
        NormalizationStatus.PARTIAL,
        NormalizationStatus.SCALE_SENSITIVE,
    }
)


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 of *payload* (sorted-key JSON).

    The digest is independent of dict ordering and of float formatting jitter
    so two structurally identical inputs hash identically across runs.
    """

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FitWindow:
    """Reference window over which a transform's parameters were fit.

    Times are integer sample indices (or epoch units) on a single monotonic
    clock. ``fit_end`` MUST NOT exceed ``apply_start``: fitting a transform on
    samples at or after the point it is applied is future-fit leakage.
    """

    fit_start: int
    fit_end: int
    apply_start: int
    apply_end: int

    def to_dict(self) -> dict[str, int]:
        return {
            "fit_start": self.fit_start,
            "fit_end": self.fit_end,
            "apply_start": self.apply_start,
            "apply_end": self.apply_end,
        }


@dataclass(frozen=True, slots=True)
class NormalizationSpec:
    """Typed normalization contract for a single claim-bearing signal."""

    signal: str
    raw_units: str
    transform: str
    fit_scope: str
    fit_window: FitWindow
    sampling_interval: int
    output_schema: tuple[str, ...]
    raw_hash: str
    transform_config_hash: str
    normalized_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "raw_units": self.raw_units,
            "transform": self.transform,
            "fit_scope": self.fit_scope,
            "fit_window": self.fit_window.to_dict(),
            "sampling_interval": self.sampling_interval,
            "output_schema": list(self.output_schema),
            "raw_hash": self.raw_hash,
            "transform_config_hash": self.transform_config_hash,
            "normalized_hash": self.normalized_hash,
        }


@dataclass(frozen=True, slots=True)
class NormalizationFinding:
    """A single fail-closed violation discovered by the validator."""

    signal: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"signal": self.signal, "code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class NormalizationReport:
    """Aggregated validator outcome for one or more specs."""

    status: NormalizationStatus
    findings: tuple[NormalizationFinding, ...]
    evidence: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "evidence": dict(self.evidence),
        }


def _spec_findings(spec: NormalizationSpec) -> list[NormalizationFinding]:
    """Return every fail-closed violation for a single spec (empty == clean)."""

    findings: list[NormalizationFinding] = []
    sig = spec.signal

    # (3a) missing units.
    if not spec.raw_units or not spec.raw_units.strip():
        findings.append(NormalizationFinding(sig, "MISSING_UNITS", "raw_units is empty"))

    # (3b) missing / unknown transform.
    if not spec.transform or not spec.transform.strip():
        findings.append(NormalizationFinding(sig, "MISSING_TRANSFORM", "transform is empty"))
    elif spec.transform not in KNOWN_TRANSFORMS:
        findings.append(
            NormalizationFinding(
                sig,
                "UNKNOWN_TRANSFORM",
                f"transform {spec.transform!r} not in {KNOWN_TRANSFORMS}",
            )
        )

    # (3c) future-fit leakage: fit window must be ordered and end no later
    # than the point of application.
    w = spec.fit_window
    if w.fit_end < w.fit_start:
        findings.append(
            NormalizationFinding(
                sig, "INVERTED_FIT_WINDOW", f"fit_end {w.fit_end} < fit_start {w.fit_start}"
            )
        )
    if w.apply_end < w.apply_start:
        findings.append(
            NormalizationFinding(
                sig,
                "INVERTED_APPLY_WINDOW",
                f"apply_end {w.apply_end} < apply_start {w.apply_start}",
            )
        )
    if w.fit_end > w.apply_start:
        findings.append(
            NormalizationFinding(
                sig,
                "FUTURE_FIT_LEAKAGE",
                f"fit_end {w.fit_end} exceeds apply_start {w.apply_start}",
            )
        )

    # (3d) inconsistent sampling.
    if spec.sampling_interval <= 0:
        findings.append(
            NormalizationFinding(
                sig,
                "INCONSISTENT_SAMPLING",
                f"sampling_interval must be positive, got {spec.sampling_interval}",
            )
        )

    # (3e) missing raw / output hash and missing output schema.
    if not spec.raw_hash or not spec.raw_hash.strip():
        findings.append(NormalizationFinding(sig, "MISSING_RAW_HASH", "raw_hash is empty"))
    if not spec.normalized_hash or not spec.normalized_hash.strip():
        findings.append(
            NormalizationFinding(sig, "MISSING_OUTPUT_HASH", "normalized_hash is empty")
        )
    if not spec.transform_config_hash or not spec.transform_config_hash.strip():
        findings.append(
            NormalizationFinding(
                sig, "MISSING_TRANSFORM_CONFIG_HASH", "transform_config_hash is empty"
            )
        )
    if not spec.output_schema:
        findings.append(
            NormalizationFinding(sig, "MISSING_OUTPUT_SCHEMA", "output_schema is empty")
        )

    return findings


def _spec_status(spec: NormalizationSpec, clean: bool) -> NormalizationStatus:
    """Per-spec status: a clean spec is NORMALIZED unless its transform is
    scale-preserving, in which case it is SCALE_SENSITIVE."""

    if not clean:
        return NormalizationStatus.PARTIAL
    if spec.transform not in SCALE_INVARIANT_TRANSFORMS:
        return NormalizationStatus.SCALE_SENSITIVE
    return NormalizationStatus.NORMALIZED


def _aggregate_status(per_spec: Sequence[NormalizationStatus]) -> NormalizationStatus:
    """Fold per-spec statuses into one fail-closed aggregate status."""

    if not per_spec:
        return NormalizationStatus.NOT_RUN
    if any(s is NormalizationStatus.PARTIAL for s in per_spec):
        return NormalizationStatus.PARTIAL
    if any(s is NormalizationStatus.SCALE_SENSITIVE for s in per_spec):
        return NormalizationStatus.SCALE_SENSITIVE
    return NormalizationStatus.NORMALIZED


def validate_normalization(
    specs: Sequence[NormalizationSpec],
) -> NormalizationReport:
    """Fail-closed validation of a set of normalization specs.

    Returns a :class:`NormalizationReport`. The aggregate status is
    ``NOT_RUN`` for an empty set, ``PARTIAL`` if any spec has a violation,
    ``SCALE_SENSITIVE`` if every spec is clean but at least one preserves raw
    scale, and ``NORMALIZED`` only when every spec is clean and scale
    invariant. Evidence carries per-signal bundle fields.
    """

    all_findings: list[NormalizationFinding] = []
    per_spec_status: list[NormalizationStatus] = []
    evidence_signals: dict[str, Any] = {}

    for spec in specs:
        findings = _spec_findings(spec)
        all_findings.extend(findings)
        status = _spec_status(spec, clean=not findings)
        per_spec_status.append(status)
        evidence_signals[spec.signal] = {
            "raw_hash": spec.raw_hash,
            "transform_config_hash": spec.transform_config_hash,
            "normalized_hash": spec.normalized_hash,
            "fit_window": spec.fit_window.to_dict(),
            "units": spec.raw_units,
            "sampling": spec.sampling_interval,
            "transform": spec.transform,
            "status": status.value,
        }

    aggregate = _aggregate_status(per_spec_status)
    evidence: dict[str, Any] = {
        "claim_boundary": NORMALIZATION_CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "signal_count": len(specs),
        "signals": evidence_signals,
    }
    evidence["evidence_hash"] = stable_hash(evidence_signals)
    return NormalizationReport(status=aggregate, findings=tuple(all_findings), evidence=evidence)


@dataclass(frozen=True, slots=True)
class AblationResult:
    """Outcome of a normalized-vs-raw fused-kernel comparison."""

    normalized_verdict: str
    raw_scale_verdict: str
    scale_invariant: bool
    status: NormalizationStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_verdict": self.normalized_verdict,
            "raw_scale_verdict": self.raw_scale_verdict,
            "scale_invariant": self.scale_invariant,
            "status": self.status.value,
        }


def raw_scale_ablation(normalized_verdict: str, raw_scale_verdict: str) -> AblationResult:
    """Compare a fused-kernel verdict on normalized vs raw-scale inputs.

    A fused-kernel claim is only ``NORMALIZED`` (scale invariant) when the
    structural verdict is identical with and without normalization. If raw
    scale flips the verdict, the claim is ``SCALE_SENSITIVE`` and MUST NOT be
    promoted.
    """

    invariant = normalized_verdict == raw_scale_verdict
    status = NormalizationStatus.NORMALIZED if invariant else NormalizationStatus.SCALE_SENSITIVE
    return AblationResult(
        normalized_verdict=normalized_verdict,
        raw_scale_verdict=raw_scale_verdict,
        scale_invariant=invariant,
        status=status,
    )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Result of the claim-promotion gate over a normalization status."""

    promoted: bool
    status: NormalizationStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted,
            "status": self.status.value,
            "reason": self.reason,
        }


def gate_claim_promotion(status: NormalizationStatus) -> PromotionDecision:
    """Refuse claim promotion when normalization status is blocking.

    A claim may be promoted only when ``status is NORMALIZED``. Any of
    ``NOT_RUN``, ``PARTIAL``, ``SCALE_SENSITIVE`` demotes the claim
    (fail-closed): absent or scale-sensitive normalization evidence is a
    blocker, not a pass.
    """

    if status in BLOCKING_STATUSES:
        return PromotionDecision(
            promoted=False,
            status=status,
            reason=f"normalization status {status.value} blocks promotion",
        )
    return PromotionDecision(
        promoted=True,
        status=status,
        reason="normalization NORMALIZED; promotion permitted",
    )


__all__ = [
    "BLOCKING_STATUSES",
    "CLAIM_BEARING_SIGNALS",
    "KNOWN_TRANSFORMS",
    "NORMALIZATION_CLAIM_BOUNDARY",
    "SCALE_INVARIANT_TRANSFORMS",
    "AblationResult",
    "FitWindow",
    "NormalizationFinding",
    "NormalizationReport",
    "NormalizationSpec",
    "NormalizationStatus",
    "PromotionDecision",
    "gate_claim_promotion",
    "raw_scale_ablation",
    "stable_hash",
    "validate_normalization",
]
