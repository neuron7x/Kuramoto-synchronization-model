# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Value-inference pipeline: the integration capstone for issue #1293.

The value-inference gates land as three independent contracts — normalization,
abstraction (:mod:`abstraction_contract`), and aggregation
(:mod:`aggregation_contract`), measured against a declared value target
(:mod:`value_target_contract`). Each one answers a *local* question. None of
them answers the *global* one: given all of their verdicts at once, may a fused
value claim be promoted, and with what calibrated confidence?

This module closes that gap. It composes five named epistemic operations into a
single deterministic, fail-closed verdict that no individual contract produces:

* **Falsify** — :func:`falsify` actively returns the stages that *break* the
  claim (``passed is False``). A claim survives only if this set is empty; we
  look for the breaker, not for confirmation on convenient stages.
* **Calibrate** — :func:`calibrate` aligns reported confidence with the actual
  per-stage support, fail-closing confidence to ``0.0`` the moment any stage
  breaks, so confidence can never exceed what the evidence carries.
* **Normalize** — :func:`normalize_weights` brings heterogeneous per-stage
  weights onto a common probability simplex, removing raw scale so only the
  relative structure of the weighting survives.
* **Adapt** — :func:`adapt` updates the calibration *temperature* toward a new
  distribution's observed accuracy: it recalibrates, it does not restructure —
  the falsification gate is invariant under adaptation.
* **Integrate** — :func:`run_pipeline` chains the four into one
  :class:`PipelineVerdict` carrying a combined confidence, the surviving-vs-
  broken stage provenance, the claim boundary, and a deterministic hash — a
  state none of the stages holds alone.

Each upstream contract reduces to a :class:`StageVerdict` (its guard's
``promoted`` flag becomes ``passed``; any continuous evidence it exposes — a
retained-information fraction, an evidence-gain magnitude — becomes
``support``). The pipeline consumes only that shape, so it stays decoupled from
the contract modules and gates the fused claim from data, not imports.

Claim boundary
--------------
This is a *value-inference integration* contract. It asserts nothing about
predictive capability, market edge, profitability, or rank. ``confidence`` is a
calibrated measure of how well the declared stages support a fused value
claim against their own declared baselines; it is not a forecast of any
outcome. The fixed boundary token below makes that explicit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Fixed claim-boundary declaration applied to every pipeline verdict. Frozen so
# the boundary cannot drift per-call.
PIPELINE_CLAIM_BOUNDARY: str = "value_inference_integration_only_not_predictor"

# Bounds for the calibration temperature. A temperature of 1.0 is the identity
# (confidence == weighted support); >1 sharpens confidence toward 1, <1 damps
# it toward 0. Bounded so adaptation can never run away.
MIN_TEMPERATURE: float = 0.1
MAX_TEMPERATURE: float = 10.0


class PipelineStatus(Enum):
    """Deterministic pipeline status used to gate the fused claim."""

    INTEGRATED = "INTEGRATED"
    DEMOTED = "DEMOTED"
    NOT_RUN = "NOT_RUN"


# Statuses that MUST block a fused value claim.
BLOCKING_PIPELINE_STATUSES: frozenset[PipelineStatus] = frozenset(
    {PipelineStatus.DEMOTED, PipelineStatus.NOT_RUN}
)


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 of *payload* (sorted-key JSON)."""

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StageVerdict:
    """The reduced public shape of one upstream contract's outcome.

    ``passed`` is the contract guard's promotion decision; ``support`` is the
    continuous evidence the stage carries on ``[0, 1]`` (e.g. a retained-
    information fraction or a normalized evidence-gain magnitude); ``weight`` is
    the stage's raw, pre-normalization importance.
    """

    name: str
    passed: bool
    support: float
    weight: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "support": self.support,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Calibration:
    """Calibration parameters mapping per-stage support to confidence.

    Only the scalar ``temperature`` is adapted; the structural falsification
    gate is never a function of it.
    """

    temperature: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"temperature": self.temperature}


def _validate_stages(stages: Sequence[StageVerdict]) -> None:
    """Fail closed on malformed stage support/weight before any computation."""

    for s in stages:
        if not 0.0 <= s.support <= 1.0:
            raise ValueError(f"stage {s.name!r} support {s.support} not in [0, 1]")
        if s.weight < 0.0:
            raise ValueError(f"stage {s.name!r} weight {s.weight} < 0")


# --- Нормалізувати / Normalize ---------------------------------------------


def normalize_weights(stages: Sequence[StageVerdict]) -> tuple[float, ...]:
    """Project heterogeneous stage weights onto the probability simplex.

    The result is non-negative and sums to 1, so stages of different raw
    scale become comparable while their *relative* proportions are preserved.
    An all-zero weight vector is a degenerate input handled explicitly (uniform
    weights), never silently divided by zero.
    """

    _validate_stages(stages)
    if not stages:
        return ()
    raw = [s.weight for s in stages]
    total = sum(raw)
    if total <= 0.0:
        # bounds: degenerate all-zero weighting → uniform simplex, not 0/0.
        return tuple(1.0 / len(stages) for _ in stages)
    return tuple(w / total for w in raw)


# --- Фальсифікувати / Falsify ----------------------------------------------


def falsify(stages: Sequence[StageVerdict]) -> tuple[StageVerdict, ...]:
    """Return the stages that break the fused claim (``passed is False``).

    Falsification-first: the pipeline asks "what breaks this?", not "what
    confirms it?". A claim may survive only when this set is empty.
    """

    return tuple(s for s in stages if not s.passed)


# --- Калібрувати / Calibrate -----------------------------------------------


def calibrate(
    stages: Sequence[StageVerdict],
    weights: Sequence[float],
    calibration: Calibration,
) -> float:
    """Return calibrated confidence in ``[0, 1]`` aligned with stage support.

    Confidence fail-closes to ``0.0`` the moment any stage breaks: a broken
    claim carries no confidence regardless of the surviving stages. Otherwise
    confidence is the weighted support raised to ``1 / temperature`` — the
    temperature sharpens (``>1``) or damps (``<1``) confidence relative to the
    raw weighted support, and is the identity at ``1.0``.
    """

    if not stages:
        return 0.0
    if falsify(stages):
        return 0.0
    if len(weights) != len(stages):
        raise ValueError(f"weights length {len(weights)} != stage count {len(stages)}")
    weighted_support = sum(w * s.support for w, s in zip(weights, stages))
    weighted_support = min(1.0, max(0.0, weighted_support))  # bounds: convex combo in [0,1]
    return weighted_support ** (1.0 / calibration.temperature)


# --- Адаптувати / Adapt ----------------------------------------------------


def adapt(
    calibration: Calibration,
    observed_accuracy: float,
    predicted_confidence: float,
    *,
    learning_rate: float = 0.5,
) -> Calibration:
    """Recalibrate the temperature toward a new distribution's observed accuracy.

    When the pipeline was over-confident (``predicted_confidence`` above the
    ``observed_accuracy`` realised on new data) the temperature is damped; when
    it was under-confident the temperature is sharpened. The update is bounded
    to ``[MIN_TEMPERATURE, MAX_TEMPERATURE]`` so adaptation cannot run away, and
    it touches only the scalar — the structural falsification gate is invariant
    under :func:`adapt`. This recalibrates; it does not restructure.
    """

    if not 0.0 <= observed_accuracy <= 1.0:
        raise ValueError(f"observed_accuracy {observed_accuracy} not in [0, 1]")
    if not 0.0 <= predicted_confidence <= 1.0:
        raise ValueError(f"predicted_confidence {predicted_confidence} not in [0, 1]")
    error = observed_accuracy - predicted_confidence
    updated = calibration.temperature * (1.0 + learning_rate * error)
    # INV: temperature bounded so adaptation is stable, never unbounded.
    updated = min(MAX_TEMPERATURE, max(MIN_TEMPERATURE, updated))
    return Calibration(temperature=updated)


# --- Інтегрувати / Integrate -----------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineVerdict:
    """Single integrated verdict over all value-inference stages."""

    status: PipelineStatus
    promoted: bool
    confidence: float
    falsifiers: tuple[str, ...]
    stage_count: int
    provenance_hash: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "promoted": self.promoted,
            "confidence": self.confidence,
            "falsifiers": list(self.falsifiers),
            "stage_count": self.stage_count,
            "provenance_hash": self.provenance_hash,
            "evidence": self.evidence,
        }


def run_pipeline(
    stages: Sequence[StageVerdict],
    calibration: Calibration | None = None,
    *,
    min_confidence: float = 0.0,
) -> PipelineVerdict:
    """Integrate the five operations into one fail-closed pipeline verdict.

    Data flow: :func:`normalize_weights` → :func:`falsify` → :func:`calibrate`,
    folded into a single :class:`PipelineVerdict`. The fused claim is promoted
    (``status is INTEGRATED``) only when stages were supplied, *no* stage
    falsifies the claim, and the calibrated confidence clears ``min_confidence``
    (the ``LOW_CONFIDENCE`` falsifier). An empty stage set is ``NOT_RUN``; any
    structural break is ``DEMOTED``. Fail-closed throughout.
    """

    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError(f"min_confidence {min_confidence} not in [0, 1]")

    calibration = calibration or Calibration()

    if not stages:
        evidence: dict[str, Any] = {
            "claim_boundary": PIPELINE_CLAIM_BOUNDARY,
            "not_predictive_claim": True,
            "stage_count": 0,
            "calibration": calibration.to_dict(),
            "stages": [],
        }
        return PipelineVerdict(
            status=PipelineStatus.NOT_RUN,
            promoted=False,
            confidence=0.0,
            falsifiers=(),
            stage_count=0,
            provenance_hash=stable_hash(evidence),
            evidence=evidence,
        )

    weights = normalize_weights(stages)
    broken = falsify(stages)
    confidence = calibrate(stages, weights, calibration)

    falsifiers = [s.name for s in broken]
    if not broken and confidence < min_confidence:
        falsifiers.append("LOW_CONFIDENCE")

    promoted = not falsifiers
    status = PipelineStatus.INTEGRATED if promoted else PipelineStatus.DEMOTED

    evidence = {
        "claim_boundary": PIPELINE_CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "stage_count": len(stages),
        "calibration": calibration.to_dict(),
        "min_confidence": min_confidence,
        "normalized_weights": list(weights),
        "stages": [s.to_dict() for s in stages],
    }
    return PipelineVerdict(
        status=status,
        promoted=promoted,
        confidence=confidence,
        falsifiers=tuple(falsifiers),
        stage_count=len(stages),
        provenance_hash=stable_hash(evidence),
        evidence=evidence,
    )


__all__ = [
    "BLOCKING_PIPELINE_STATUSES",
    "MAX_TEMPERATURE",
    "MIN_TEMPERATURE",
    "PIPELINE_CLAIM_BOUNDARY",
    "Calibration",
    "PipelineStatus",
    "PipelineVerdict",
    "StageVerdict",
    "adapt",
    "calibrate",
    "falsify",
    "normalize_weights",
    "run_pipeline",
    "stable_hash",
]
