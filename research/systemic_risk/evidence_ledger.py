# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bayesian evidence ledger — confidence as a function of evidence.

Operationalises § 2 of the canonical-7 charter
(``feedback_hypothesis_destruction_machine.md`` + the formal-spec
patches issued 2026-05-08): confidence in a claim is *not*
narrative — it is the posterior log-odds after a sequence of
typed evidence records, each carrying an explicit Bayes factor.

Update law (Cox 1946; Jaynes 2003 §4.4):

.. math::

    \\log\\text{odds}(\\text{posterior}_n)
        = \\log\\text{odds}(\\text{prior}) + \\sum_{j \\le n} \\log \\mathrm{BF}_j

Silence is forbidden — every evidence entry must carry a Bayes
factor (``BF = 1`` is the explicit *uninformative* mark; absent
entries are a contract violation).

Pure-function API. No I/O. Determinism via explicit ``seed`` on
the producing layer; this module is itself state-free under
:class:`EvidenceLedger.with_evidence`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

__all__ = [
    "EvidenceType",
    "TierAction",
    "Evidence",
    "LedgerEntry",
    "EvidenceLedger",
    "DEFAULT_PRIOR_LOG_ODDS",
    "DOWNGRADE_TRIGGER_DELTA",
    "KILL_TRIGGER_LOG_ODDS",
    "auc_per_crisis_bayes_factor",
    "baseline_dominance_bayes_factor",
    "replication_match_bayes_factor",
    "external_review_bayes_factor",
]


EvidenceType = Literal[
    "AUC_PER_CRISIS",
    "LEAKAGE_POSITIVE",
    "PARAMETER_FRAGILITY",
    "BASELINE_DOMINANCE",
    "REPLICATION_MATCH",
    "REPLICATION_MISMATCH",
    "EXTERNAL_REVIEW_POSITIVE",
    "EXTERNAL_REVIEW_NEGATIVE",
    "UNINFORMATIVE",
]


TierAction = Literal[
    "NONE",
    "DEMOTE",
    "QUARANTINE",
    "INVALIDATE",
    "KILL",
]


# Default prior set by the literature meta-prior on interbank
# phase-locking signals (Acemoglu-Ozdaglar-Tahbaz-Salehi 2015,
# Bardoscia 2021): the claim is *not* the default expectation.
# log_odds = -1.0 ⇒ probability ≈ 0.27.
DEFAULT_PRIOR_LOG_ODDS: float = -1.0

# Threshold (in log-odds) below which the posterior triggers a
# tier downgrade per § 1 of the charter.
DOWNGRADE_TRIGGER_DELTA: float = 1.0

# Posterior log-odds at which the kill trigger fires.
KILL_TRIGGER_LOG_ODDS: float = -5.0

# Per-evidence Bayes-factor cap (in log-odds magnitude). Prevents
# a single record from dominating the posterior.
_MAX_LOG_BF: float = 10.0


# ---------------------------------------------------------------------------
# Bayes-factor calculators (per evidence type)
# ---------------------------------------------------------------------------


def auc_per_crisis_bayes_factor(auc: float, n_crises: int) -> float:
    """Wilcoxon-asymptotic Bayes factor for a per-crisis AUC reading.

    For a candidate vs. null, the U-statistic asymptotic normal
    approximation gives ``log BF ∝ 2 (AUC - 0.5) sqrt(n)``.
    Capped at ±:data:`_MAX_LOG_BF` log-odds so a single AUC reading
    cannot crash through the kill trigger by itself.

    Caller must supply ``auc ∈ [0, 1]`` and ``n_crises ≥ 1``.
    """
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"auc must be in [0, 1], got {auc}")
    if n_crises < 1:
        raise ValueError(f"n_crises must be >= 1, got {n_crises}")
    log_bf = 2.0 * (auc - 0.5) * math.sqrt(n_crises)
    log_bf = max(-_MAX_LOG_BF, min(_MAX_LOG_BF, log_bf))
    return math.exp(log_bf)


def baseline_dominance_bayes_factor(delta: float, n_pairs: int) -> float:
    """Bayes factor for a candidate-vs-baseline AUC delta.

    ``delta > 0`` means candidate beat baseline; positive evidence.
    ``delta = 0`` is informative against the candidate (Occam: a
    baseline at parity is the disconfirming explanation).
    Capped at ±:data:`_MAX_LOG_BF`.
    """
    if n_pairs < 1:
        raise ValueError(f"n_pairs must be >= 1, got {n_pairs}")
    log_bf = 2.0 * delta * math.sqrt(n_pairs)
    log_bf = max(-_MAX_LOG_BF, min(_MAX_LOG_BF, log_bf))
    return math.exp(log_bf)


def replication_match_bayes_factor(*, matched: bool) -> float:
    """100:1 odds when a capsule rerun matches; 0 (kill) when it doesn't."""
    return 100.0 if matched else 0.0


def external_review_bayes_factor(*, positive: bool) -> float:
    """10:1 in favour for a positive external review; 0.1 for negative."""
    return 10.0 if positive else 0.1


# ---------------------------------------------------------------------------
# Typed records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Evidence:
    """One typed evidence record with its Bayes factor.

    Attributes
    ----------
    timestamp_utc
        ISO-8601 UTC timestamp at the moment the evidence was
        sealed. Must precede every subsequent record on the same
        claim.
    type
        One of :data:`EvidenceType`.
    bayes_factor
        Bayes factor of the evidence for the claim. ``BF = 0.0``
        is degenerate (kill trigger); ``BF = 1.0`` is uninformative.
    payload
        Free-form JSON-serialisable mapping of the evidence
        contents (e.g. ``{"auc": 0.74, "n_crises": 3}``).
    source_run_sha
        Optional SHA of the run manifest that produced this
        evidence; ties the entry to a replication capsule.
    """

    timestamp_utc: str
    type: EvidenceType
    bayes_factor: float
    payload: dict[str, float | int | str | bool] = field(default_factory=dict)
    source_run_sha: str | None = None

    def __post_init__(self) -> None:
        if self.bayes_factor < 0.0 or not math.isfinite(self.bayes_factor):
            raise ValueError(f"bayes_factor must be finite and >= 0, got {self.bayes_factor}")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Aggregate state for one claim id."""

    claim_id: str
    prior_log_odds: float
    evidence: tuple[Evidence, ...]
    posterior_log_odds: float

    @property
    def posterior_probability(self) -> float:
        """Posterior probability via the logistic transform."""
        try:
            return 1.0 / (1.0 + math.exp(-self.posterior_log_odds))
        except OverflowError:
            return 0.0 if self.posterior_log_odds < 0 else 1.0

    @property
    def tier_action(self) -> TierAction:
        """Aggregate tier action implied by the posterior + evidence stream.

        Precedence (charter § 1):
        ``KILL > INVALIDATE > QUARANTINE > DEMOTE > NONE``.

        This module emits ``KILL`` and ``DEMOTE`` directly. The
        other actions are produced by triggers in
        ``death_conditions.py`` that consume external signals
        (leakage sentinel, parameter fragility, data firewall).
        """
        # Kill: any degenerate evidence OR posterior beneath the
        # kill threshold.
        if any(e.bayes_factor == 0.0 for e in self.evidence):
            return "KILL"
        if self.posterior_log_odds <= KILL_TRIGGER_LOG_ODDS:
            return "KILL"
        # Demote: posterior fell more than DOWNGRADE_TRIGGER_DELTA
        # below the prior.
        if self.posterior_log_odds < self.prior_log_odds - DOWNGRADE_TRIGGER_DELTA:
            return "DEMOTE"
        return "NONE"


# ---------------------------------------------------------------------------
# Public ledger API
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Frozen evidence ledger keyed by ``claim_id``.

    Updates produce a *new* ledger via :meth:`with_evidence`; the
    immutability is an explicit design constraint — a mutable
    ledger would let the posterior change without an audit trail.
    """

    entries: dict[str, LedgerEntry] = field(default_factory=dict)

    def get(self, claim_id: str) -> LedgerEntry | None:
        return self.entries.get(claim_id)

    def with_claim(
        self,
        claim_id: str,
        *,
        prior_log_odds: float = DEFAULT_PRIOR_LOG_ODDS,
    ) -> "EvidenceLedger":
        """Return a new ledger seeded with ``claim_id`` at the given prior."""
        if claim_id in self.entries:
            raise ValueError(f"claim_id={claim_id!r} already present in ledger")
        entry = LedgerEntry(
            claim_id=claim_id,
            prior_log_odds=float(prior_log_odds),
            evidence=tuple(),
            posterior_log_odds=float(prior_log_odds),
        )
        new_entries = dict(self.entries)
        new_entries[claim_id] = entry
        return EvidenceLedger(entries=new_entries)

    def with_evidence(
        self,
        claim_id: str,
        evidence: Evidence,
    ) -> "EvidenceLedger":
        """Append ``evidence`` to ``claim_id`` and return the updated ledger.

        Fails closed if:

        * ``claim_id`` is not seeded (caller must use
          :meth:`with_claim` first — silent claim creation is
          forbidden).
        * ``evidence.timestamp_utc`` does not strictly succeed the
          most recent record (chronological-only; back-dating
          evidence is a contract violation).
        """
        existing = self.entries.get(claim_id)
        if existing is None:
            raise ValueError(f"claim_id={claim_id!r} not seeded; call with_claim first")
        if existing.evidence:
            last_ts = existing.evidence[-1].timestamp_utc
            if evidence.timestamp_utc <= last_ts:
                raise ValueError(
                    f"evidence timestamp {evidence.timestamp_utc} must "
                    f"strictly succeed previous {last_ts}"
                )
        # Posterior update via log-odds sum.
        if evidence.bayes_factor == 0.0:
            new_log_odds = -math.inf
        else:
            new_log_odds = existing.posterior_log_odds + math.log(evidence.bayes_factor)
            # Numeric clamp to KILL_TRIGGER_LOG_ODDS - 1.0 on the
            # negative side so finite arithmetic cannot bypass the
            # kill threshold.
            if not math.isfinite(new_log_odds):
                new_log_odds = KILL_TRIGGER_LOG_ODDS - 1.0 if evidence.bayes_factor < 1.0 else 100.0
        new_entry = LedgerEntry(
            claim_id=claim_id,
            prior_log_odds=existing.prior_log_odds,
            evidence=existing.evidence + (evidence,),
            posterior_log_odds=float(new_log_odds),
        )
        new_entries = dict(self.entries)
        new_entries[claim_id] = new_entry
        return EvidenceLedger(entries=new_entries)


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp helper — used by callers when they don't
    want to invent a timestamp themselves."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# Suppress unused-symbol warning — exported helper.
_ = _utc_now_iso
