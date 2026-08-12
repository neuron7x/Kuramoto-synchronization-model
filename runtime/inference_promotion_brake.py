from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Sequence

from runtime.hyperdirect_veto import (
    HyperdirectConfig,
    HyperdirectVeto,
    HyperdirectVetoError,
    VetoDecision,
)

__all__ = [
    "InferenceClaim",
    "PromotionVerdict",
    "InferencePromotionBrake",
]


@dataclass(frozen=True)
class InferenceClaim:
    """A claim asking to be promoted from a verified context onto an
    extrapolated one.

    ``hypothesis_score`` and ``null_scores`` produce the evidence margin
    ``hypothesis_score - max(null_scores)`` — how far the claim's own
    statistic beats its strongest null. The remaining fields are the
    **residual** conflict channels (HDV-007): signals a caller asserts
    are NOT already hard-gated by an upstream contract. Any channel left
    ``None`` is simply absent — the brake never invents a channel.
    """

    hypothesis_score: float
    null_scores: Sequence[float]
    falsifier_disagreement: float | None = None
    witness_uncertainty: float | None = None
    purpose_drift: float | None = None
    external_falsification_drift: float | None = None


@dataclass(frozen=True)
class PromotionVerdict:
    """Advisory outcome. ``advisory`` is always True by construction.

    This brake never mutates execution, never writes state, and is not
    on any trading/execution path. A consumer is free to ignore it; it
    only *reports* whether the claim cleared the hyperdirect brake.
    """

    promote: bool
    evidence_margin: float
    decision: VetoDecision
    advisory: bool = True


class InferencePromotionBrake:
    """Maps an :class:`InferenceClaim` onto :class:`HyperdirectVeto`.

    Pure and stateless. The mapping is deliberately thin: it computes the
    evidence margin, collects only the residual conflict channels that
    were actually supplied, and delegates the decision wholesale to
    HyperdirectVeto. No scoring logic, no thresholds of its own — the
    brake's behaviour is exactly the primitive's behaviour, so there is
    no second place for drift to hide.

    What a ``promote=True`` verdict means: under the caller-supplied
    score, nulls, and residual conflict, no single-channel STOP fired
    and the margin cleared the conflict-proportional bar. It does NOT
    assert the inputs correspond to reality, nor that acting on the
    claim is safe — that obligation stays upstream. The verdict is
    advisory: a recommendation, never an authorisation.
    """

    def __init__(self, config: HyperdirectConfig | None = None) -> None:
        self._veto = HyperdirectVeto(config)

    @property
    def config(self) -> HyperdirectConfig:
        return self._veto.config

    def assess(self, claim: InferenceClaim) -> PromotionVerdict:
        if not isinstance(claim, InferenceClaim):
            raise HyperdirectVetoError("promotion denied: claim must be an InferenceClaim")

        hypothesis = self._finite(
            claim.hypothesis_score,
            "promotion denied: hypothesis_score must be a finite real",
        )
        nulls = tuple(claim.null_scores)
        if not nulls:
            raise HyperdirectVetoError("promotion denied: at least one null score is required")
        max_null = max(
            self._finite(v, "promotion denied: every null score must be a finite real")
            for v in nulls
        )
        evidence_margin = hypothesis - max_null

        conflict: dict[str, float] = {}
        for name, value in (
            ("falsifier_disagreement", claim.falsifier_disagreement),
            ("witness_uncertainty", claim.witness_uncertainty),
            ("purpose_drift", claim.purpose_drift),
            ("external_falsification_drift", claim.external_falsification_drift),
        ):
            if value is not None:
                # Range/finiteness is enforced by the primitive (HDV-004),
                # so there is exactly one validation site, not two.
                conflict[name] = value

        decision = self._veto.evaluate(conflict, evidence_margin=evidence_margin)
        return PromotionVerdict(
            promote=decision.passed,
            evidence_margin=evidence_margin,
            decision=decision,
        )

    @staticmethod
    def _finite(value: object, message: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise HyperdirectVetoError(message)
        try:
            if not isfinite(value):  # type: ignore[arg-type]
                raise HyperdirectVetoError(message)
        except (TypeError, ValueError) as exc:
            raise HyperdirectVetoError(message) from exc
        return float(value)
