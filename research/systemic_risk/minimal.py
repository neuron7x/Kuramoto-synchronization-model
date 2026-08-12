# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Minimal Canonical Seven — single-file, <800 LoC, NamedTuple-based.

A complete reimplementation of the seven canonical pillars
optimised for *speed of thought* and *minimum boilerplate*. Every
value type is a :class:`typing.NamedTuple`; every state machine is a
pure function; the public surface is **8 names**.

Use this module when:

* you are *writing* research (interactive REPL, notebooks);
* you need the canonical pipeline in a tight loop without dataclass
  ceremony;
* you teach the canonical seven and want a single artefact to point
  at.

Do *not* use this for production audit — the verbose modules
(``death_conditions``, ``evidence_ledger``, ``data_firewall`` etc.)
provide richer audit trails, full Provenance objects and
property-tested invariants. ``minimal`` is the *interactive* front;
those are the *forensic* front.

Pillars (mapping to the verbose modules)
=========================================
* P1 ``death`` (death engine)            ↔ ``death_conditions``
* P2 ``ledger`` (Bayesian update)        ↔ ``evidence_ledger``
* P3 ``firewall`` (data gate)            ↔ ``data_firewall``
* P4 ``ladder`` (adversarial prosecutors)↔ ``adversarial_ladder``
* P5 ``leak`` (leakage sentinels)        ↔ ``leakage_sentinel``
* P6 ``rerun`` (replication)             ↔ ``replication_capsule``
* P7 ``fsm`` (governance lifecycle)      ↔ ``governance_fsm``

Public symbols (8): :data:`KILL`, :data:`INVALIDATE`,
:data:`QUARANTINE`, :data:`DEMOTE`, :data:`STOP`, :data:`NONE`
[these six are aliases of :class:`TierAction`], :class:`Claim`
(NamedTuple state), :func:`evaluate` (one-call orchestrator).

Pure-function API. No I/O. No mutation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date
from enum import IntEnum
from typing import Final, NamedTuple

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "DEMOTE",
    "INVALIDATE",
    "KILL",
    "NONE",
    "QUARANTINE",
    "STOP",
    "Claim",
    "TierAction",
    "evaluate",
]


# ============================================================================
# 0. Action algebra (totally ordered lattice; join = max)
# ============================================================================


class TierAction(IntEnum):
    """The six canonical tier actions, totally ordered by destructiveness.

    The *join* (max) of a multiset of actions yields the precedence
    rule ``KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE``.
    """

    NONE = 0
    STOP = 1
    DEMOTE = 2
    QUARANTINE = 3
    INVALIDATE = 4
    KILL = 5


# Bare-name aliases for ergonomics.
NONE: Final = TierAction.NONE
STOP: Final = TierAction.STOP
DEMOTE: Final = TierAction.DEMOTE
QUARANTINE: Final = TierAction.QUARANTINE
INVALIDATE: Final = TierAction.INVALIDATE
KILL: Final = TierAction.KILL


# ============================================================================
# 1. Claim state (NamedTuple) — the unified ledger + FSM + posterior
# ============================================================================


class Claim(NamedTuple):
    """The complete state of one claim under canonical-seven evaluation.

    Combines four concerns that the verbose modules split across
    multiple frozen dataclasses:

    * tier (governance FSM state, integer in 0..7 per
      ``GOV_LADDER`` below)
    * posterior (log-odds; current Bayesian belief)
    * evidence_count (audit trail length)
    * last_action (the most recent :class:`TierAction` applied)

    NamedTuple gives us frozen-by-construction, ``slots``-equivalent
    memory layout, full type checking, and zero dataclass ceremony.
    """

    claim_id: str
    tier: int
    posterior_log_odds: float
    evidence_count: int
    last_action: TierAction


# ============================================================================
# 2. Governance ladder — 8 promotable states + REJECTED + QUARANTINED
# ============================================================================


GOV_LADDER: Final[tuple[str, ...]] = (
    "IDEA",  # 0
    "HYPOTHESIS",  # 1
    "INSTRUMENTED",  # 2
    "TESTED_SYNTHETIC",  # 3
    "TESTED_REAL",  # 4
    "MEASURED",  # 5
    "REPLICATED",  # 6
    "VALIDATED",  # 7
)
QUARANTINED: Final[int] = -1  # frozen, off-ladder
REJECTED: Final[int] = -2  # absorbing terminal


def state_name(tier: int) -> str:
    """Map an integer tier to its canonical name."""
    if tier == QUARANTINED:
        return "QUARANTINED"
    if tier == REJECTED:
        return "REJECTED"
    if 0 <= tier < len(GOV_LADDER):
        return GOV_LADDER[tier]
    raise ValueError(f"unknown tier integer {tier!r}")


# ============================================================================
# 3. Bayes-factor calculators (rigorous; replaces ad hoc forms)
# ============================================================================


_BIC_CAP: Final[float] = 20.0  # numeric stability cap on |log BF|


def _wagenmakers_bf(z: float, n_eff: float) -> float:
    """BIC-derived Bayes factor (Wagenmakers 2007).

    log BF_10 ≈ (z² - log n_eff) / 2; clamped to ±20 for stability.
    """
    log_bf = (z * z - math.log(n_eff)) / 2.0
    log_bf = max(-_BIC_CAP, min(_BIC_CAP, log_bf))
    return float(math.exp(log_bf))


def auc_bf(auc: float, *, n_pos: int, n_neg: int) -> float:
    """Mann-Whitney null-variance → Wagenmakers BIC-BF.

    Source: Mann & Whitney 1947; Bamber 1975; Wagenmakers 2007.
    """
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"auc must be in [0, 1], got {auc}")
    if n_pos < 1 or n_neg < 1:
        raise ValueError(f"n_pos, n_neg must be >= 1; got {n_pos}, {n_neg}")
    sigma = math.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    z = (auc - 0.5) / sigma
    n_eff = float(n_pos) * float(n_neg) / float(n_pos + n_neg + 1)
    return _wagenmakers_bf(z, n_eff)


def replication_bf(matched: bool) -> float:
    """Replication BF: 100 on match, 0 on mismatch (drives KILL)."""
    return 100.0 if matched else 0.0


# ============================================================================
# 4. Pillar 3 — Data Reality Firewall (8 gates as a single function)
# ============================================================================


def firewall(
    panels: Mapping[date, NDArray[np.float64]],
    n_nodes: int,
) -> tuple[bool, str]:
    """Run all 8 firewall gates; return (passed_all, reason).

    Gates: schema_type, shape, finite, sign, diagonal, sparsity,
    monotonic_time, provenance (provenance is checked separately
    via :func:`firewall_provenance` to keep this signature lean).
    """
    if not panels:
        return False, "G1: panels empty"
    keys = list(panels.keys())
    for k in keys:
        if not isinstance(k, date):
            return False, f"G1: non-date key {k!r}"
    for k, v in panels.items():
        if not isinstance(v, np.ndarray) or v.dtype != np.float64:
            return False, f"G1: {k}: not ndarray[float64]"
        if v.ndim != 2 or v.shape != (n_nodes, n_nodes):
            return False, f"G2: {k}: shape {v.shape}"
        if not np.all(np.isfinite(v)):
            return False, f"G3: {k}: NaN/Inf"
        if np.any(v < 0):
            return False, f"G4: {k}: negative entries"
        if np.any(np.diagonal(v) != 0):
            return False, f"G5: {k}: non-zero diagonal"
        if not np.any(v != 0):
            return False, f"G6: {k}: all-zero matrix"
    for prev, curr in zip(keys, keys[1:]):
        if curr <= prev:
            return False, f"G7: dates not strictly increasing {prev} → {curr}"
    return True, "all 8 gates passed"


# ============================================================================
# 5. Pillar 5 — Leakage sentinel (6 checks as one function)
# ============================================================================


_FORBIDDEN_CENTERED: Final[frozenset[str]] = frozenset(
    {"center", "centered", "centre", "lookahead"}
)
_FORBIDDEN_FULLSAMPLE: Final[frozenset[str]] = frozenset(
    {
        "full_sample_zscore",
        "full_sample_normalize",
        "full_sample_demean",
        "full_sample_scale",
        "full_sample_minmax",
        "global_zscore",
    }
)


def leakage(
    *,
    config: Mapping[str, object] | None = None,
    op_log: Iterable[str] | None = None,
    op_graph: Iterable[tuple[str, int, int]] | None = None,
    min_lead_time: int | None = None,
    crisis_lock_utc: str | None = None,
    first_eval_utc: str | None = None,
) -> tuple[bool, str]:
    """Six independent leakage sentinels in one function.

    Returns (detected, reason). detected=True means the upstream
    pipeline must NOT continue.
    """
    if config is not None:
        for k in _FORBIDDEN_CENTERED:
            if k in config and config[k]:
                return True, f"S3: forbidden centered key {k!r}"
        if config.get("align") == "center":
            return True, "S3: align=center"
        offset = config.get("offset")
        if isinstance(offset, (int, float)) and offset > 0:
            return True, f"S3: positive offset {offset}"
    if op_log is not None:
        for op in op_log:
            if op in _FORBIDDEN_FULLSAMPLE:
                return True, f"S4: forbidden op {op!r}"
    if op_graph is not None:
        for name, t_in, t_out in op_graph:
            if t_out < t_in:
                return True, f"S5: backwards edge in {name!r} ({t_in}→{t_out})"
    if min_lead_time is not None and min_lead_time < 1:
        return True, f"S2: post-event contamination, lead={min_lead_time}"
    if crisis_lock_utc is not None and first_eval_utc is not None:
        try:
            from datetime import datetime

            lock = datetime.fromisoformat(crisis_lock_utc)
            evl = datetime.fromisoformat(first_eval_utc)
        except ValueError:
            return True, "S6: timestamp parse failure"
        if lock >= evl:
            return True, f"S6: crisis_date_tuning lock={lock} >= eval={evl}"
    return False, "all 6 sentinels clean"


# ============================================================================
# 6. Pillar 6 — Replication capsule (one comparator)
# ============================================================================


def rerun(
    *,
    primary_metric: float,
    secondary_metric: float,
    primary_seed: int,
    secondary_seed: int,
    primary_config_hash: str,
    secondary_config_hash: str,
    tolerance: float = 1e-12,
) -> tuple[bool, str]:
    """Compare two runs; return (matched, reason).

    Six-stage fail-closed: tolerance ≥ 0 / both metrics finite /
    config_hash match / seed match / |Δ| ≤ tolerance.
    """
    if tolerance < 0:
        return False, "tolerance_negative"
    if not math.isfinite(primary_metric):
        return False, "non_finite_primary_metric"
    if not math.isfinite(secondary_metric):
        return False, "non_finite_secondary_metric"
    if primary_config_hash != secondary_config_hash:
        return False, "config_hash_diverged"
    if primary_seed != secondary_seed:
        return False, "seed_diverged"
    if abs(primary_metric - secondary_metric) > tolerance:
        return False, "metric_deviation_exceeds_tolerance"
    return True, "matched"


# ============================================================================
# 7. Pillar 1+7 — Death engine + Governance FSM (unified state machine)
# ============================================================================


def _next_tier_after_demote(tier: int) -> int:
    if tier == QUARANTINED:
        return 0  # demote-from-quarantine resets to IDEA
    if tier <= 0:
        return 0  # clamp at IDEA
    return tier - 1


def evaluate(
    claim: Claim,
    *,
    # Pillar 4 — adversarial ladder
    losing_paths: tuple[str, ...] | None = None,
    # Pillar 5 — leakage
    leakage_detected: bool | None = None,
    # Pillar 4 sub — fragility
    fragile: bool | None = None,
    # Pillar 6 — replication
    replication_matched: bool | None = None,
    # Pillar 3 — firewall
    firewall_passed_all: bool | None = None,
    # Pillar 2 — Bayes-factor evidence
    new_evidence_log_bf: float | None = None,
) -> Claim:
    """Drive a claim through one canonical-seven round.

    Single entry point; folds together all seven pillars. Each
    optional argument corresponds to one pillar's outcome:

    * ``losing_paths`` (tuple) → DEMOTE if non-empty (P4).
    * ``leakage_detected`` (bool) → INVALIDATE if True (P5).
    * ``fragile`` (bool) → QUARANTINE if True (P3-fragility).
    * ``replication_matched`` (bool) → KILL if False (P6).
    * ``firewall_passed_all`` (bool) → STOP if False (P3).
    * ``new_evidence_log_bf`` (float) → updates Bayesian posterior (P2).

    The action precedence is the *join* (max) of the lattice order
    KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE; this is
    encoded by :class:`TierAction` being :class:`IntEnum`.

    REJECTED is absorbing — a claim already at REJECTED stays
    REJECTED regardless of inputs (no resurrection).

    Returns a *new* :class:`Claim` (NamedTuple is immutable by
    construction).
    """
    if claim.tier == REJECTED:
        return claim._replace(last_action=NONE)

    actions: list[TierAction] = []
    if losing_paths is not None and losing_paths:
        actions.append(DEMOTE)
    if leakage_detected:
        actions.append(INVALIDATE)
    if fragile:
        actions.append(QUARANTINE)
    if replication_matched is False:
        actions.append(KILL)
    if firewall_passed_all is False:
        actions.append(STOP)

    action: TierAction = max(actions) if actions else NONE

    new_tier = claim.tier
    if action == KILL:
        new_tier = REJECTED
    elif action == INVALIDATE:
        new_tier = 0  # IDEA
    elif action == QUARANTINE:
        new_tier = QUARANTINED
    elif action == DEMOTE:
        new_tier = _next_tier_after_demote(claim.tier)
    # STOP / NONE leave tier unchanged

    new_posterior = claim.posterior_log_odds
    new_count = claim.evidence_count
    if new_evidence_log_bf is not None:
        if not math.isfinite(new_evidence_log_bf):
            raise ValueError(f"new_evidence_log_bf must be finite, got {new_evidence_log_bf}")
        new_posterior = claim.posterior_log_odds + new_evidence_log_bf
        new_count = claim.evidence_count + 1
        # Posterior-floor → KILL (decision-theoretic threshold; default
        # corresponds to c_FK / c_FP ≈ 1/148, see bayes_rigorous.py).
        if new_posterior <= -5.0 and action != KILL:
            new_tier = REJECTED
            action = KILL

    return Claim(
        claim_id=claim.claim_id,
        tier=new_tier,
        posterior_log_odds=new_posterior,
        evidence_count=new_count,
        last_action=action,
    )


def initial_claim(claim_id: str, prior_log_odds: float = -1.0) -> Claim:
    """Construct a fresh :class:`Claim` at tier IDEA with the supplied prior.

    Default prior log-odds = −1.0 corresponds to P(H) ≈ 0.269 (soft
    skepticism); see ``evidence_ledger.DEFAULT_PRIOR_LOG_ODDS`` for
    the verbose-module equivalent.
    """
    return Claim(
        claim_id=claim_id,
        tier=0,  # IDEA
        posterior_log_odds=prior_log_odds,
        evidence_count=0,
        last_action=NONE,
    )
