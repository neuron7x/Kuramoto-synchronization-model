# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable aggregation contract for fused signal artifacts.

GeoSync fuses heterogeneous structural descriptors into a single aggregate
market-state tensor::

    returns + L2 liquidity + Ricci field + Kuramoto phase + volatility
    + cost state  ->  aggregate market-state tensor  ->  fused fragility
    validation.

A fused artifact is only trustworthy if the fusion is *auditable*: every
input signal must declare its schema, its timestamp-alignment policy, its
provenance hash, and its normalization status; the aggregate must carry a
content hash; and the fused result must demonstrate that it actually adds
information over the standalone signals and over a null-fusion baseline.
Absent that demonstration, "the fusion says X" is an unfalsifiable assertion.

This module converts aggregation from documentation into executable
validation behaviour. It provides:

* a typed :class:`SignalArtifact` per input (schema, timestamps,
  alignment policy, provenance hash, normalization status);
* a fail-closed :func:`validate_aggregation` that rejects unknown alignment
  policies, missing schema / provenance hash, misaligned timestamps under a
  strict policy, and inputs whose normalization status is not ``NORMALIZED``;
* :func:`aggregate_state_hash` producing a deterministic content hash over
  the aligned, provenance-bound inputs;
* :func:`evidence_gain` comparing a fused score against the best standalone
  signal and against a null-fusion baseline;
* a :func:`guard_aggregation_claim` claim-card guard that demotes an
  aggregation claim when the evidence gain is absent or normalization is
  incomplete.

Claim boundary
--------------
This is an *aggregation-integrity* contract. It asserts nothing about
predictive capability, market edge, profitability, or rank. ``evidence_gain``
measures information added by fusion relative to a declared baseline; it is
not a profitability or forecast metric. The fixed boundary token below makes
that explicit so a downstream reader cannot mistake fusion bookkeeping for a
forecast.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Fixed claim-boundary declaration applied to every aggregation evidence
# bundle. Frozen so the boundary cannot drift per-call.
AGGREGATION_CLAIM_BOUNDARY: str = "aggregation_integrity_only_not_predictor"

# Canonical fused-signal inputs the aggregation contract governs. Mirrors the
# target chain in issue #1292.
FUSED_SIGNAL_INPUTS: tuple[str, ...] = (
    "returns",
    "l2_liquidity",
    "ricci_field",
    "kuramoto_phase",
    "volatility",
    "cost_state",
)

# Recognised timestamp-alignment policies.
KNOWN_ALIGNMENT_POLICIES: tuple[str, ...] = (
    "exact",  # every signal must share an identical timestamp grid
    "resample_floor",  # signals resampled down to a common interval (declared)
    "as_of_join",  # last-known value carried forward to a reference clock
)


class SignalNormalizationStatus(Enum):
    """Per-signal normalization status (reuses the #1290 contract vocabulary).

    Kept as a local enum so the aggregation contract is self-contained and
    does not couple its import graph to the normalization module; the string
    values are identical to ``NormalizationStatus`` so the two contracts
    interoperate at the evidence-bundle layer.
    """

    NORMALIZED = "NORMALIZED"
    SCALE_SENSITIVE = "SCALE_SENSITIVE"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


class AggregationStatus(Enum):
    """Deterministic aggregation status used to gate claim promotion."""

    AGGREGATED = "AGGREGATED"
    NO_EVIDENCE_GAIN = "NO_EVIDENCE_GAIN"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


# Statuses that MUST block an aggregation claim.
BLOCKING_AGGREGATION_STATUSES: frozenset[AggregationStatus] = frozenset(
    {
        AggregationStatus.NOT_RUN,
        AggregationStatus.PARTIAL,
        AggregationStatus.NO_EVIDENCE_GAIN,
    }
)


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 of *payload* (sorted-key JSON)."""

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SignalArtifact:
    """Typed per-signal input to the aggregation contract."""

    name: str
    schema: tuple[str, ...]
    timestamps: tuple[int, ...]
    alignment_policy: str
    provenance_hash: str
    normalization_status: SignalNormalizationStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema": list(self.schema),
            "timestamps": list(self.timestamps),
            "alignment_policy": self.alignment_policy,
            "provenance_hash": self.provenance_hash,
            "normalization_status": self.normalization_status.value,
        }


@dataclass(frozen=True, slots=True)
class AggregationFinding:
    """A single fail-closed violation discovered by the validator."""

    signal: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"signal": self.signal, "code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class AggregationReport:
    """Aggregated validator outcome over a set of signal artifacts."""

    status: AggregationStatus
    findings: tuple[AggregationFinding, ...]
    aggregate_hash: str
    evidence: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "aggregate_hash": self.aggregate_hash,
            "findings": [f.to_dict() for f in self.findings],
            "evidence": dict(self.evidence),
        }


def _artifact_findings(artifact: SignalArtifact) -> list[AggregationFinding]:
    """Return every fail-closed violation for a single artifact."""

    findings: list[AggregationFinding] = []
    name = artifact.name

    if not artifact.schema:
        findings.append(AggregationFinding(name, "MISSING_SCHEMA", "schema is empty"))
    if not artifact.provenance_hash or not artifact.provenance_hash.strip():
        findings.append(
            AggregationFinding(name, "MISSING_PROVENANCE_HASH", "provenance_hash is empty")
        )
    if artifact.alignment_policy not in KNOWN_ALIGNMENT_POLICIES:
        findings.append(
            AggregationFinding(
                name,
                "UNKNOWN_ALIGNMENT_POLICY",
                f"{artifact.alignment_policy!r} not in {KNOWN_ALIGNMENT_POLICIES}",
            )
        )
    if not artifact.timestamps:
        findings.append(AggregationFinding(name, "MISSING_TIMESTAMPS", "timestamps is empty"))
    elif list(artifact.timestamps) != sorted(artifact.timestamps):
        findings.append(
            AggregationFinding(
                name, "UNSORTED_TIMESTAMPS", "timestamps are not monotonically sorted"
            )
        )
    if artifact.normalization_status is not SignalNormalizationStatus.NORMALIZED:
        findings.append(
            AggregationFinding(
                name,
                "NORMALIZATION_INCOMPLETE",
                f"normalization status {artifact.normalization_status.value} != NORMALIZED",
            )
        )

    return findings


def _alignment_findings(artifacts: Sequence[SignalArtifact]) -> list[AggregationFinding]:
    """Cross-signal timestamp-alignment policy enforcement.

    Under the ``exact`` policy every contributing signal MUST share an
    identical timestamp grid; a mismatch is a fail-closed misalignment.
    """

    findings: list[AggregationFinding] = []
    exact = [a for a in artifacts if a.alignment_policy == "exact"]
    if len(exact) >= 2:
        reference = exact[0].timestamps
        for a in exact[1:]:
            if a.timestamps != reference:
                findings.append(
                    AggregationFinding(
                        a.name,
                        "TIMESTAMP_MISALIGNMENT",
                        f"timestamps differ from reference {exact[0].name!r} under exact policy",
                    )
                )
    return findings


def aggregate_state_hash(artifacts: Sequence[SignalArtifact]) -> str:
    """Deterministic content hash over the provenance-bound input set.

    Order-independent (artifacts sorted by name) so the same input set always
    hashes identically regardless of supply order.
    """

    payload = [
        {
            "name": a.name,
            "schema": list(a.schema),
            "alignment_policy": a.alignment_policy,
            "provenance_hash": a.provenance_hash,
            "normalization_status": a.normalization_status.value,
        }
        for a in sorted(artifacts, key=lambda x: x.name)
    ]
    return stable_hash(payload)


@dataclass(frozen=True, slots=True)
class EvidenceGain:
    """Standalone-vs-aggregate comparison against a null-fusion baseline."""

    fused_score: float
    best_standalone_score: float
    null_fusion_score: float
    gain_over_standalone: float
    gain_over_null: float
    has_gain: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fused_score": self.fused_score,
            "best_standalone_score": self.best_standalone_score,
            "null_fusion_score": self.null_fusion_score,
            "gain_over_standalone": self.gain_over_standalone,
            "gain_over_null": self.gain_over_null,
            "has_gain": self.has_gain,
        }


def evidence_gain(
    fused_score: float,
    standalone_scores: Mapping[str, float],
    null_fusion_score: float,
    *,
    tolerance: float = 1e-9,
) -> EvidenceGain:
    """Quantify the information added by fusion.

    A fused artifact has evidence gain only when its score *strictly* exceeds
    both the best standalone signal and the null-fusion baseline (by more than
    ``tolerance``). Equality or regression means fusion added nothing — the
    claim must demote, not pass. With no standalone scores the best-standalone
    floor is treated as ``-inf`` so the null-fusion comparison still governs.
    """

    best_standalone = max(standalone_scores.values()) if standalone_scores else float("-inf")
    gain_over_standalone = fused_score - best_standalone
    gain_over_null = fused_score - null_fusion_score
    has_gain = (gain_over_standalone > tolerance) and (gain_over_null > tolerance)
    return EvidenceGain(
        fused_score=fused_score,
        best_standalone_score=best_standalone,
        null_fusion_score=null_fusion_score,
        gain_over_standalone=gain_over_standalone,
        gain_over_null=gain_over_null,
        has_gain=has_gain,
    )


def validate_aggregation(
    artifacts: Sequence[SignalArtifact],
    gain: EvidenceGain | None = None,
) -> AggregationReport:
    """Fail-closed validation of a fused-signal aggregation.

    The aggregate status is ``NOT_RUN`` for an empty input set, ``PARTIAL`` if
    any per-signal or alignment violation exists, ``NO_EVIDENCE_GAIN`` if the
    inputs are clean but the supplied evidence gain is absent (or no gain was
    supplied), and ``AGGREGATED`` only when inputs are clean *and* fusion shows
    evidence gain.
    """

    findings: list[AggregationFinding] = []
    for a in artifacts:
        findings.extend(_artifact_findings(a))
    findings.extend(_alignment_findings(artifacts))

    agg_hash = aggregate_state_hash(artifacts)

    if not artifacts:
        status = AggregationStatus.NOT_RUN
    elif findings:
        status = AggregationStatus.PARTIAL
    elif gain is None or not gain.has_gain:
        status = AggregationStatus.NO_EVIDENCE_GAIN
    else:
        status = AggregationStatus.AGGREGATED

    evidence: dict[str, Any] = {
        "claim_boundary": AGGREGATION_CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "signal_count": len(artifacts),
        "aggregate_hash": agg_hash,
        "signals": {a.name: a.to_dict() for a in artifacts},
        "evidence_gain": gain.to_dict() if gain is not None else None,
    }
    return AggregationReport(
        status=status,
        findings=tuple(findings),
        aggregate_hash=agg_hash,
        evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class AggregationClaimCard:
    """Result of the claim-card guard over an aggregation report."""

    promoted: bool
    status: AggregationStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted,
            "status": self.status.value,
            "reason": self.reason,
        }


def guard_aggregation_claim(report: AggregationReport) -> AggregationClaimCard:
    """Demote an aggregation claim unless it is fully supported.

    A claim may be promoted only when ``status is AGGREGATED`` (clean inputs +
    evidence gain). ``NOT_RUN``, ``PARTIAL``, ``NO_EVIDENCE_GAIN`` all demote
    (fail-closed): absent fusion benefit is a blocker, not a pass.
    """

    if report.status in BLOCKING_AGGREGATION_STATUSES:
        return AggregationClaimCard(
            promoted=False,
            status=report.status,
            reason=f"aggregation status {report.status.value} blocks promotion",
        )
    return AggregationClaimCard(
        promoted=True,
        status=report.status,
        reason="aggregation AGGREGATED with evidence gain; promotion permitted",
    )


__all__ = [
    "AGGREGATION_CLAIM_BOUNDARY",
    "BLOCKING_AGGREGATION_STATUSES",
    "FUSED_SIGNAL_INPUTS",
    "KNOWN_ALIGNMENT_POLICIES",
    "AggregationClaimCard",
    "AggregationFinding",
    "AggregationReport",
    "AggregationStatus",
    "EvidenceGain",
    "SignalArtifact",
    "SignalNormalizationStatus",
    "aggregate_state_hash",
    "evidence_gain",
    "guard_aggregation_claim",
    "stable_hash",
    "validate_aggregation",
]
