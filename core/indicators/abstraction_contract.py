# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable abstraction contract for reduced signal representations.

GeoSync repeatedly *abstracts* a raw, high-dimensional representation into a
compact descriptor::

    raw L2 order book        -> liquidity-depth descriptor
    raw price path           -> Hurst / fractal exponent
    full coupling matrix     -> Kuramoto order parameter
    raw curvature field       -> Ricci summary statistic

Such an abstraction is only worth its cost if it does two things at once:
it *reduces* the representation cost (fewer units to carry, store, and reason
about) **and** it *retains* the value-relevant information of the source above
a declared floor. An abstraction that compresses but discards the signal is a
silent fidelity loss; an abstraction that retains the signal but does not
shrink anything is a relabelling, not a reduction. Either way the claim that
"the abstraction is worth its cost" is unfalsifiable unless both halves are
measured.

This module is the abstraction half of the value-inference gates in issue
#1293 (the aggregation half lives in :mod:`aggregation_contract`, the value
target + evidence-gain metric in :mod:`value_target_contract`). It converts
abstraction from documentation into executable, fail-closed behaviour and
provides:

* a typed :class:`AbstractionArtifact` per reduction step (source dimension,
  abstracted dimension, retained-information fraction, fidelity floor,
  abstraction method, provenance hash);
* a fail-closed validator that rejects unknown methods, missing provenance,
  non-positive dimensions, and out-of-range fidelity fractions;
* :func:`compute_abstraction_gain` quantifying compression ratio and whether
  the step both compresses and clears its fidelity floor;
* :func:`abstraction_state_hash` producing a deterministic content hash over
  the provenance-bound reduction set;
* :func:`guard_abstraction_claim`, a claim-card guard that demotes an
  abstraction claim when any step fails to reduce cost or drops below its
  declared fidelity floor.

Claim boundary
--------------
This is an *abstraction-fidelity* contract. It asserts nothing about
predictive capability, market edge, profitability, or rank. The retained
fraction is the caller's declared, run-local fidelity of the reduced
representation against its own source; it is not a forecast or a quality
score for any downstream outcome. The fixed boundary token below makes that
explicit so a reader cannot mistake reduction bookkeeping for a forecast.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Fixed claim-boundary declaration applied to every abstraction evidence
# bundle. Frozen so the boundary cannot drift per-call.
ABSTRACTION_CLAIM_BOUNDARY: str = "abstraction_fidelity_only_not_predictor"

# Canonical abstraction steps the contract governs. Mirrors the reduction
# chain described in the module docstring.
ABSTRACTION_TARGETS: tuple[str, ...] = (
    "l2_liquidity_descriptor",
    "hurst_exponent",
    "kuramoto_order_parameter",
    "ricci_summary",
)

# Recognised abstraction methods. An unknown method is a fail-closed finding:
# an unaudited reduction cannot be trusted to retain what it claims.
KNOWN_ABSTRACTION_METHODS: tuple[str, ...] = (
    "summary_statistic",  # raw field -> scalar / low-rank summary
    "spectral_reduction",  # eigen / spectral projection to fewer modes
    "order_parameter",  # collective-state collapse (e.g. Kuramoto R)
    "fractal_exponent",  # self-similarity exponent of a raw path
    "windowed_descriptor",  # rolling-window feature over a raw stream
)


class AbstractionStatus(Enum):
    """Deterministic abstraction status used to gate claim promotion."""

    ABSTRACTED = "ABSTRACTED"
    NO_COMPRESSION = "NO_COMPRESSION"
    FIDELITY_LOSS = "FIDELITY_LOSS"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


# Statuses that MUST block an abstraction claim.
BLOCKING_ABSTRACTION_STATUSES: frozenset[AbstractionStatus] = frozenset(
    {
        AbstractionStatus.NOT_RUN,
        AbstractionStatus.PARTIAL,
        AbstractionStatus.NO_COMPRESSION,
        AbstractionStatus.FIDELITY_LOSS,
    }
)


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 of *payload* (sorted-key JSON)."""

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AbstractionArtifact:
    """Typed per-step input to the abstraction contract.

    ``source_dim`` and ``abstracted_dim`` are the representation costs before
    and after the reduction (in caller-defined units, e.g. features, modes,
    or book levels). ``retained_information`` is the caller's declared fraction
    of value-relevant information the reduced representation preserves, and
    ``fidelity_floor`` is the minimum fraction the run requires for the step to
    count as worth its cost. Both fractions live in ``[0, 1]``.
    """

    name: str
    source_dim: int
    abstracted_dim: int
    retained_information: float
    fidelity_floor: float
    method: str
    provenance_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_dim": self.source_dim,
            "abstracted_dim": self.abstracted_dim,
            "retained_information": self.retained_information,
            "fidelity_floor": self.fidelity_floor,
            "method": self.method,
            "provenance_hash": self.provenance_hash,
        }


@dataclass(frozen=True, slots=True)
class AbstractionFinding:
    """A single fail-closed violation discovered by the validator."""

    step: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"step": self.step, "code": self.code, "detail": self.detail}


def _artifact_findings(artifact: AbstractionArtifact) -> list[AbstractionFinding]:
    """Return every fail-closed violation for a single abstraction step."""

    findings: list[AbstractionFinding] = []
    name = artifact.name

    if not artifact.provenance_hash or not artifact.provenance_hash.strip():
        findings.append(
            AbstractionFinding(name, "MISSING_PROVENANCE_HASH", "provenance_hash is empty")
        )
    if artifact.method not in KNOWN_ABSTRACTION_METHODS:
        findings.append(
            AbstractionFinding(
                name,
                "UNKNOWN_METHOD",
                f"{artifact.method!r} not in {KNOWN_ABSTRACTION_METHODS}",
            )
        )
    if artifact.source_dim <= 0:
        findings.append(
            AbstractionFinding(
                name, "NONPOSITIVE_SOURCE_DIM", f"source_dim {artifact.source_dim} <= 0"
            )
        )
    if artifact.abstracted_dim <= 0:
        findings.append(
            AbstractionFinding(
                name,
                "NONPOSITIVE_ABSTRACTED_DIM",
                f"abstracted_dim {artifact.abstracted_dim} <= 0",
            )
        )
    if not 0.0 <= artifact.retained_information <= 1.0:
        findings.append(
            AbstractionFinding(
                name,
                "RETAINED_OUT_OF_RANGE",
                f"retained_information {artifact.retained_information} not in [0, 1]",
            )
        )
    if not 0.0 <= artifact.fidelity_floor <= 1.0:
        findings.append(
            AbstractionFinding(
                name,
                "FLOOR_OUT_OF_RANGE",
                f"fidelity_floor {artifact.fidelity_floor} not in [0, 1]",
            )
        )

    return findings


@dataclass(frozen=True, slots=True)
class AbstractionGain:
    """Compression-vs-fidelity outcome for a single abstraction step."""

    name: str
    source_dim: int
    abstracted_dim: int
    compression_ratio: float
    retained_information: float
    fidelity_floor: float
    has_compression: bool
    retains_fidelity: bool
    worth_cost: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_dim": self.source_dim,
            "abstracted_dim": self.abstracted_dim,
            "compression_ratio": self.compression_ratio,
            "retained_information": self.retained_information,
            "fidelity_floor": self.fidelity_floor,
            "has_compression": self.has_compression,
            "retains_fidelity": self.retains_fidelity,
            "worth_cost": self.worth_cost,
        }


def compute_abstraction_gain(
    artifact: AbstractionArtifact, *, tolerance: float = 1e-9
) -> AbstractionGain:
    """Quantify whether one abstraction step is worth its cost.

    A step is worth its cost only when it *strictly* reduces representation
    cost (``compression_ratio = source_dim / abstracted_dim > 1`` by more than
    ``tolerance``) **and** retains information at or above its declared
    fidelity floor. A reduction that merely relabels (ratio ≤ 1) or that
    compresses below the floor adds no defensible value — the claim must
    demote, not pass.

    Assumes the artifact already passed :func:`_artifact_findings`; callers go
    through :func:`validate_abstraction`, which only computes gain for clean
    inputs (``abstracted_dim`` is therefore positive here).
    """

    compression_ratio = artifact.source_dim / artifact.abstracted_dim
    has_compression = compression_ratio > 1.0 + tolerance
    retains_fidelity = artifact.retained_information + tolerance >= artifact.fidelity_floor
    return AbstractionGain(
        name=artifact.name,
        source_dim=artifact.source_dim,
        abstracted_dim=artifact.abstracted_dim,
        compression_ratio=compression_ratio,
        retained_information=artifact.retained_information,
        fidelity_floor=artifact.fidelity_floor,
        has_compression=has_compression,
        retains_fidelity=retains_fidelity,
        worth_cost=has_compression and retains_fidelity,
    )


def abstraction_state_hash(artifacts: Sequence[AbstractionArtifact]) -> str:
    """Deterministic content hash over the provenance-bound reduction set.

    Order-independent (artifacts sorted by name) so the same reduction set
    always hashes identically regardless of supply order.
    """

    payload = [
        {
            "name": a.name,
            "source_dim": a.source_dim,
            "abstracted_dim": a.abstracted_dim,
            "retained_information": a.retained_information,
            "fidelity_floor": a.fidelity_floor,
            "method": a.method,
            "provenance_hash": a.provenance_hash,
        }
        for a in sorted(artifacts, key=lambda x: x.name)
    ]
    return stable_hash(payload)


@dataclass(frozen=True, slots=True)
class AbstractionReport:
    """Aggregated validator outcome over a set of abstraction steps."""

    status: AbstractionStatus
    findings: tuple[AbstractionFinding, ...]
    gains: tuple[AbstractionGain, ...]
    abstraction_hash: str
    evidence: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "abstraction_hash": self.abstraction_hash,
            "findings": [f.to_dict() for f in self.findings],
            "gains": [g.to_dict() for g in self.gains],
            "evidence": dict(self.evidence),
        }


def validate_abstraction(
    artifacts: Sequence[AbstractionArtifact], *, tolerance: float = 1e-9
) -> AbstractionReport:
    """Fail-closed validation of a set of abstraction steps.

    The status is ``NOT_RUN`` for an empty set, ``PARTIAL`` if any per-step
    violation exists, ``NO_COMPRESSION`` if the inputs are clean but at least
    one step fails to reduce cost, ``FIDELITY_LOSS`` if every step compresses
    but at least one drops below its fidelity floor, and ``ABSTRACTED`` only
    when every step is clean, compresses, and clears its floor.

    Compression is checked before fidelity so a step that neither shrinks nor
    retains is reported as ``NO_COMPRESSION`` (the more fundamental failure).
    """

    findings: list[AbstractionFinding] = []
    for a in artifacts:
        findings.extend(_artifact_findings(a))

    abstraction_hash = abstraction_state_hash(artifacts)

    gains: tuple[AbstractionGain, ...] = ()
    if not artifacts:
        status = AbstractionStatus.NOT_RUN
    elif findings:
        status = AbstractionStatus.PARTIAL
    else:
        gains = tuple(compute_abstraction_gain(a, tolerance=tolerance) for a in artifacts)
        if not all(g.has_compression for g in gains):
            status = AbstractionStatus.NO_COMPRESSION
        elif not all(g.retains_fidelity for g in gains):
            status = AbstractionStatus.FIDELITY_LOSS
        else:
            status = AbstractionStatus.ABSTRACTED

    evidence: dict[str, Any] = {
        "claim_boundary": ABSTRACTION_CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "step_count": len(artifacts),
        "abstraction_hash": abstraction_hash,
        "steps": {a.name: a.to_dict() for a in artifacts},
        "gains": [g.to_dict() for g in gains],
    }
    return AbstractionReport(
        status=status,
        findings=tuple(findings),
        gains=gains,
        abstraction_hash=abstraction_hash,
        evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class AbstractionClaimCard:
    """Result of the claim-card guard over an abstraction report."""

    promoted: bool
    status: AbstractionStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted,
            "status": self.status.value,
            "reason": self.reason,
        }


def guard_abstraction_claim(report: AbstractionReport) -> AbstractionClaimCard:
    """Demote an abstraction claim unless every step is worth its cost.

    A claim may be promoted only when ``status is ABSTRACTED`` (clean inputs,
    every step compresses, every step clears its fidelity floor). ``NOT_RUN``,
    ``PARTIAL``, ``NO_COMPRESSION``, and ``FIDELITY_LOSS`` all demote
    (fail-closed): a reduction that does not pay for itself is a blocker, not a
    pass.
    """

    if report.status in BLOCKING_ABSTRACTION_STATUSES:
        return AbstractionClaimCard(
            promoted=False,
            status=report.status,
            reason=f"abstraction status {report.status.value} blocks promotion",
        )
    return AbstractionClaimCard(
        promoted=True,
        status=report.status,
        reason="abstraction ABSTRACTED: every step compresses and clears its fidelity floor",
    )


__all__ = [
    "ABSTRACTION_CLAIM_BOUNDARY",
    "ABSTRACTION_TARGETS",
    "BLOCKING_ABSTRACTION_STATUSES",
    "KNOWN_ABSTRACTION_METHODS",
    "AbstractionArtifact",
    "AbstractionClaimCard",
    "AbstractionFinding",
    "AbstractionGain",
    "AbstractionReport",
    "AbstractionStatus",
    "abstraction_state_hash",
    "compute_abstraction_gain",
    "guard_abstraction_claim",
    "stable_hash",
    "validate_abstraction",
]
