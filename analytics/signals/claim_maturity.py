# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable claim-maturity ladder for descriptor research lines.

A descriptor claim does not become trustworthy because someone *says* it is
mature. It becomes mature only when each evidence rung beneath it actually
exists. This module makes that ladder executable: a fourteen-rung ordered
state machine where every promotion is gated on the concrete evidence the
target rung demands, and **no rung may be skipped**.

The ladder (ascending)::

    UNOBSERVED
    OBSERVABLE
    MEASURED_SYNTHETIC
    ALTERNATIVES_ENUMERATED
    DISCRIMINATING_TEST_DEFINED
    FALSIFIER_EXECUTED
    CALIBRATED
    INTEGRATED
    REPLAYABLE
    REAL_DATA_SINGLE_SESSION
    REAL_DATA_MULTI_SESSION
    ALTERNATIVES_ELIMINATED
    NEGATIVE_EVIDENCE_PRESERVED
    BOUNDED_CLAIM_ALLOWED

:func:`evaluate_promotion` answers, deterministically and fail-closed,
whether a claim may move from its current rung to a target rung given a set
of satisfied evidence tokens. Promotion is allowed only when **every**
intermediate rung's evidence requirement is met — a request that would skip
an unmet rung is reported as blocked, with the exact missing
``(state, evidence)`` pairs preserved as negative evidence.

The hard rules encoded here mirror the governance contract:

* no real-data maturity (``REAL_DATA_SINGLE_SESSION`` and above) without a
  real-data artifact and its provenance;
* no ``ALTERNATIVES_ELIMINATED`` without both a null comparison and a
  simpler-baseline comparison;
* no ``BOUNDED_CLAIM_ALLOWED`` without the explicit conjunction of replay
  digest, provenance, executed falsifier, and a preserved negative-evidence
  path.

This is a governance gate, not a predictor. A ``BOUNDED_CLAIM_ALLOWED``
verdict states only that a *descriptor* claim has cleared its evidence
ladder; it carries no predictive, significance, or financial meaning, and
every verdict declares ``claim_boundary="descriptor_only_not_predictor"``.

Determinism
-----------
:func:`evaluate_promotion` is a pure function of ``(current, target,
evidence)``. There is no clock, no randomness, and no global state, so the
same arguments always yield the same verdict and the same sorted
``missing_evidence``.

Fail-closed
-----------
An unknown state name, a target that is not strictly above the current
state, or an unrecognised evidence token raises :class:`ValueError`. A
mistyped evidence token is rejected loudly rather than silently leaving a
requirement unmet and a typo masquerading as satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

__all__ = [
    "CLAIM_BOUNDARY",
    "LADDER",
    "EVIDENCE_REQUIREMENTS",
    "EVIDENCE_VOCABULARY",
    "PromotionVerdict",
    "evaluate_promotion",
]

#: The single declared boundary string shared by every verdict.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"

#: The fourteen-rung maturity ladder, ascending. Index == rung height.
LADDER: tuple[str, ...] = (
    "UNOBSERVED",
    "OBSERVABLE",
    "MEASURED_SYNTHETIC",
    "ALTERNATIVES_ENUMERATED",
    "DISCRIMINATING_TEST_DEFINED",
    "FALSIFIER_EXECUTED",
    "CALIBRATED",
    "INTEGRATED",
    "REPLAYABLE",
    "REAL_DATA_SINGLE_SESSION",
    "REAL_DATA_MULTI_SESSION",
    "ALTERNATIVES_ELIMINATED",
    "NEGATIVE_EVIDENCE_PRESERVED",
    "BOUNDED_CLAIM_ALLOWED",
)

#: Evidence each rung demands to be *entered* from the rung below. The base
#: rung ``UNOBSERVED`` is the ground state and demands nothing. Tuples carry
#: AND semantics: every token listed must be satisfied. The top rung
#: re-asserts the full bounded-claim conjunction so the strongest claim
#: cannot be reached without replay, provenance, an executed falsifier, and
#: a preserved negative-evidence path — even if an earlier rung's token were
#: ever relaxed.
EVIDENCE_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    "UNOBSERVED": (),
    "OBSERVABLE": ("observability",),
    "MEASURED_SYNTHETIC": ("synthetic_measurement",),
    "ALTERNATIVES_ENUMERATED": ("alternatives_enumerated",),
    "DISCRIMINATING_TEST_DEFINED": ("discriminating_test",),
    "FALSIFIER_EXECUTED": ("falsifier_executed",),
    "CALIBRATED": ("calibration_record",),
    "INTEGRATED": ("integration_proof",),
    "REPLAYABLE": ("replay_digest",),
    "REAL_DATA_SINGLE_SESSION": ("real_data_artifact", "provenance"),
    "REAL_DATA_MULTI_SESSION": ("real_data_multi_session",),
    "ALTERNATIVES_ELIMINATED": ("null_comparison", "simpler_baseline_comparison"),
    "NEGATIVE_EVIDENCE_PRESERVED": ("negative_evidence_path",),
    "BOUNDED_CLAIM_ALLOWED": (
        "replay_digest",
        "provenance",
        "falsifier_executed",
        "negative_evidence_path",
    ),
}

#: The closed vocabulary of evidence tokens. Any token outside this set is a
#: typo or an unsupported claim and is rejected rather than silently ignored.
EVIDENCE_VOCABULARY: frozenset[str] = frozenset(
    token for tokens in EVIDENCE_REQUIREMENTS.values() for token in tokens
)

_RANK: Mapping[str, int] = {state: index for index, state in enumerate(LADDER)}


@dataclass(frozen=True, slots=True)
class PromotionVerdict:
    """Immutable verdict of a single promotion evaluation.

    ``allowed`` is ``True`` only when every rung strictly above ``current``
    up to and including ``target`` has all of its evidence satisfied.
    ``missing_evidence`` is the sorted tuple of ``(state, evidence_token)``
    pairs that block the promotion, preserved as negative evidence even when
    the promotion is refused. ``blocked_at`` is the lowest rung that is
    missing evidence, or ``None`` when the promotion is allowed.
    """

    current_state: str
    target_state: str
    allowed: bool
    satisfied_rungs: tuple[str, ...]
    missing_evidence: tuple[tuple[str, str], ...]
    blocked_at: str | None
    claim_boundary: str = CLAIM_BOUNDARY

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping with deterministic key ordering."""
        return {
            "current_state": self.current_state,
            "target_state": self.target_state,
            "allowed": self.allowed,
            "satisfied_rungs": list(self.satisfied_rungs),
            "missing_evidence": [list(pair) for pair in self.missing_evidence],
            "blocked_at": self.blocked_at,
            "claim_boundary": self.claim_boundary,
        }


def _require_state(name: Any, role: str) -> str:
    if not isinstance(name, str) or name not in _RANK:
        raise ValueError(
            f"claim-maturity: {role} must be one of the {len(LADDER)} ladder states, got {name!r}"
        )
    return name


def _validate_evidence(evidence: Iterable[str]) -> frozenset[str]:
    if isinstance(evidence, (str, bytes)):
        raise ValueError("claim-maturity: evidence must be a collection of tokens, not a string")
    tokens = frozenset(evidence)
    unknown = sorted(t for t in tokens if t not in EVIDENCE_VOCABULARY)
    if unknown:
        raise ValueError(
            f"claim-maturity: unknown evidence token(s) {unknown!r}; reject rather than skip"
        )
    return tokens


def evaluate_promotion(
    current_state: str,
    target_state: str,
    evidence: Iterable[str],
) -> PromotionVerdict:
    """Evaluate whether a claim may be promoted from ``current`` to ``target``.

    Promotion is allowed only when ``target_state`` is strictly above
    ``current_state`` on :data:`LADDER` and every rung in
    ``(current_state, target_state]`` has all of its
    :data:`EVIDENCE_REQUIREMENTS` satisfied by ``evidence`` — no rung may be
    skipped. The set of unmet ``(state, token)`` requirements is preserved in
    ``missing_evidence`` even when the promotion is refused.

    Raises :class:`ValueError` on an unknown state, a target that is not
    strictly above the current state, or an unrecognised evidence token.
    """
    current = _require_state(current_state, "current_state")
    target = _require_state(target_state, "target_state")
    if _RANK[target] <= _RANK[current]:
        raise ValueError(
            f"claim-maturity: target {target!r} (rank {_RANK[target]}) is not a promotion above "
            f"current {current!r} (rank {_RANK[current]}); promotion must move strictly up"
        )
    have = _validate_evidence(evidence)

    satisfied: list[str] = []
    missing: list[tuple[str, str]] = []
    # Walk every rung from current+1 up to and including target. A rung is
    # satisfied only when ALL of its required tokens are present; the first
    # rung with any gap is the binding blocker, but we collect every gap so
    # the report is a complete negative-evidence ledger, not just the first.
    for rung in LADDER[_RANK[current] + 1 : _RANK[target] + 1]:
        rung_gaps = [token for token in EVIDENCE_REQUIREMENTS[rung] if token not in have]
        if rung_gaps:
            missing.extend((rung, token) for token in rung_gaps)
        else:
            satisfied.append(rung)

    missing_sorted = tuple(sorted(missing))
    blocked_at = missing_sorted[0][0] if missing_sorted else None
    return PromotionVerdict(
        current_state=current,
        target_state=target,
        allowed=not missing_sorted,
        satisfied_rungs=tuple(satisfied),
        missing_evidence=missing_sorted,
        blocked_at=blocked_at,
    )
