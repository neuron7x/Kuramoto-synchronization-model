# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable value-inference gates: value target + evidence-gain metric.

Abstraction and aggregation are only worth their cost if they add *value* over
the standalone modules they fuse. This module makes that an executable gate
(issue #1293): a run must declare what value target it is being measured
against, what role each signal plays, and whether fusion actually beats both
the best standalone module and a null-fusion baseline. When the gain is
absent, the claim is **demoted**, not passed.

Provides:

* a typed :class:`ValueTarget` declared per run (name, direction, unit,
  reference baseline policy);
* a :class:`SignalRole` contract per signal (the role it plays in the fused
  estimate, plus its standalone score on the same target);
* :func:`compute_value_inference` producing an :class:`InferenceGain`
  (fused vs best-standalone vs null-fusion) and an
  :class:`InferenceVerdict` (`SUPPORTED` / `DEMOTED_NO_GAIN` /
  `DEMOTED_INCOMPLETE` / `NOT_RUN`);
* :func:`ablation_report` enumerating per-signal leave-one-in deltas;
* :func:`value_report` — a single deterministic dict (the one-command value
  report payload).

Claim boundary
--------------
This is a *value-attribution* contract. ``InferenceGain`` measures whether
fusion improves a declared, run-local value target relative to declared
baselines. It asserts nothing about forecast skill, ranking of future
outcomes, profitability, or market edge — the value target is whatever the
caller declares and is compared only against the caller's own standalone
modules and a null-fusion baseline. The fixed boundary token below (and the
``not_predictive_rank`` flag on the report) makes that explicit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Fixed claim-boundary declaration applied to every value report. Frozen so
# the boundary cannot drift per-call.
VALUE_CLAIM_BOUNDARY: str = "value_attribution_only_not_predictive_rank"


class ValueDirection(Enum):
    """Whether a larger or smaller value-target score is "better"."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class InferenceVerdict(Enum):
    """Deterministic value-inference verdict (fail-closed)."""

    SUPPORTED = "SUPPORTED"
    DEMOTED_NO_GAIN = "DEMOTED_NO_GAIN"
    DEMOTED_INCOMPLETE = "DEMOTED_INCOMPLETE"
    NOT_RUN = "NOT_RUN"


# Verdicts that block a value claim.
BLOCKING_VERDICTS: frozenset[InferenceVerdict] = frozenset(
    {
        InferenceVerdict.DEMOTED_NO_GAIN,
        InferenceVerdict.DEMOTED_INCOMPLETE,
        InferenceVerdict.NOT_RUN,
    }
)


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 of *payload* (sorted-key JSON)."""

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ValueTarget:
    """The declared value target a run is measured against.

    ``direction`` fixes the sense of "better"; ``baseline_policy`` names how
    the null-fusion baseline was constructed (e.g. ``best_single``,
    ``mean_of_standalones``). Both are recorded so the comparison is
    auditable, not implied.
    """

    name: str
    direction: ValueDirection
    unit: str
    baseline_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction.value,
            "unit": self.unit,
            "baseline_policy": self.baseline_policy,
        }


@dataclass(frozen=True, slots=True)
class SignalRole:
    """Role contract for one signal contributing to the fused estimate."""

    name: str
    role: str
    standalone_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "standalone_score": self.standalone_score,
        }


@dataclass(frozen=True, slots=True)
class InferenceGain:
    """Fused-vs-standalone-vs-null gain on a declared value target."""

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


def _oriented(direction: ValueDirection, value: float) -> float:
    """Map a raw score to a higher-is-better orientation.

    For ``LOWER_IS_BETTER`` the score is negated so that strict ``>`` always
    means "better" downstream — the gain logic stays direction-agnostic.
    """

    if direction is ValueDirection.LOWER_IS_BETTER:
        return -value
    return value


def _best_standalone(direction: ValueDirection, roles: Sequence[SignalRole]) -> float:
    """Return the best standalone score under the target's direction.

    Raw (un-oriented) value of the best module; with no roles the floor is the
    worst possible oriented score so the null comparison still governs.
    """

    if not roles:
        return float("-inf") if direction is ValueDirection.HIGHER_IS_BETTER else float("inf")
    return max(
        (r.standalone_score for r in roles),
        key=lambda v: _oriented(direction, v),
    )


def compute_inference_gain(
    target: ValueTarget,
    fused_score: float,
    roles: Sequence[SignalRole],
    null_fusion_score: float,
    *,
    tolerance: float = 1e-9,
) -> InferenceGain:
    """Quantify the value fusion adds over standalone modules and the null.

    Gain exists only when the fused score is *strictly* better (by more than
    ``tolerance``, under the target's direction) than BOTH the best standalone
    module AND the null-fusion baseline. Ties or regressions ⇒ no gain ⇒ the
    claim must demote.
    """

    best = _best_standalone(target.direction, roles)
    of = _oriented(target.direction, fused_score)
    gain_over_standalone = of - _oriented(target.direction, best)
    gain_over_null = of - _oriented(target.direction, null_fusion_score)
    has_gain = (gain_over_standalone > tolerance) and (gain_over_null > tolerance)
    return InferenceGain(
        fused_score=fused_score,
        best_standalone_score=best,
        null_fusion_score=null_fusion_score,
        gain_over_standalone=gain_over_standalone,
        gain_over_null=gain_over_null,
        has_gain=has_gain,
    )


@dataclass(frozen=True, slots=True)
class AblationEntry:
    """Leave-one-in standalone contribution for a single signal."""

    name: str
    role: str
    standalone_score: float
    delta_vs_best_other: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "standalone_score": self.standalone_score,
            "delta_vs_best_other": self.delta_vs_best_other,
        }


def ablation_report(target: ValueTarget, roles: Sequence[SignalRole]) -> tuple[AblationEntry, ...]:
    """Per-signal ablation: each signal's oriented delta vs the best other.

    A positive ``delta_vs_best_other`` means the signal is the strongest
    standalone contributor under the target's direction.
    """

    entries: list[AblationEntry] = []
    for r in roles:
        others = [o for o in roles if o.name != r.name]
        best_other = _best_standalone(target.direction, others)
        delta = _oriented(target.direction, r.standalone_score) - _oriented(
            target.direction, best_other
        )
        entries.append(
            AblationEntry(
                name=r.name,
                role=r.role,
                standalone_score=r.standalone_score,
                delta_vs_best_other=delta,
            )
        )
    return tuple(entries)


def _verdict(
    roles: Sequence[SignalRole], gain: InferenceGain, normalization_ok: bool
) -> InferenceVerdict:
    """Fold roles + gain + upstream normalization status into a verdict."""

    if not roles:
        return InferenceVerdict.NOT_RUN
    if not normalization_ok:
        return InferenceVerdict.DEMOTED_INCOMPLETE
    if not gain.has_gain:
        return InferenceVerdict.DEMOTED_NO_GAIN
    return InferenceVerdict.SUPPORTED


@dataclass(frozen=True, slots=True)
class ValueInferenceResult:
    """Outcome of the value-inference gate for a single run."""

    target: ValueTarget
    verdict: InferenceVerdict
    gain: InferenceGain
    ablation: tuple[AblationEntry, ...]
    promoted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "verdict": self.verdict.value,
            "gain": self.gain.to_dict(),
            "ablation": [a.to_dict() for a in self.ablation],
            "promoted": self.promoted,
        }


def compute_value_inference(
    target: ValueTarget,
    fused_score: float,
    roles: Sequence[SignalRole],
    null_fusion_score: float,
    *,
    normalization_ok: bool = True,
    tolerance: float = 1e-9,
) -> ValueInferenceResult:
    """Run the full value-inference gate.

    Promotes a value claim only when the run declares roles, upstream
    normalization is complete, and fusion shows strict gain over both the best
    standalone module and the null-fusion baseline. Any other case demotes.
    """

    gain = compute_inference_gain(
        target, fused_score, roles, null_fusion_score, tolerance=tolerance
    )
    verdict = _verdict(roles, gain, normalization_ok)
    return ValueInferenceResult(
        target=target,
        verdict=verdict,
        gain=gain,
        ablation=ablation_report(target, roles),
        promoted=verdict is InferenceVerdict.SUPPORTED,
    )


def value_report(result: ValueInferenceResult) -> dict[str, Any]:
    """Return the deterministic one-command value-report payload.

    The payload is sorted-key-JSON hashable (``report_hash``) so two identical
    runs produce identical bytes, and it carries the fixed claim boundary so a
    reader cannot mistake value attribution for a forecast.
    """

    body: dict[str, Any] = {
        "claim_boundary": VALUE_CLAIM_BOUNDARY,
        "not_predictive_rank": True,
        "target": result.target.to_dict(),
        "verdict": result.verdict.value,
        "promoted": result.promoted,
        "gain": result.gain.to_dict(),
        "ablation": [a.to_dict() for a in result.ablation],
    }
    body["report_hash"] = stable_hash({k: v for k, v in body.items() if k != "report_hash"})
    return body


def build_value_report(
    target: ValueTarget,
    fused_score: float,
    roles: Sequence[SignalRole],
    null_fusion_score: float,
    *,
    normalization_ok: bool = True,
    tolerance: float = 1e-9,
) -> Mapping[str, Any]:
    """One-command convenience: compute the gate and emit its value report."""

    result = compute_value_inference(
        target,
        fused_score,
        roles,
        null_fusion_score,
        normalization_ok=normalization_ok,
        tolerance=tolerance,
    )
    return value_report(result)


__all__ = [
    "BLOCKING_VERDICTS",
    "VALUE_CLAIM_BOUNDARY",
    "AblationEntry",
    "InferenceGain",
    "InferenceVerdict",
    "SignalRole",
    "ValueDirection",
    "ValueInferenceResult",
    "ValueTarget",
    "ablation_report",
    "build_value_report",
    "compute_inference_gain",
    "compute_value_inference",
    "stable_hash",
    "value_report",
]
