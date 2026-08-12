# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pre-registered falsification battery — v2 with bootstrap-CI verdict.

The hypothesis under test (``HYPOTHESIS`` tier per ``CLAIMS.md``):

    The early-warning score
    (:func:`research.systemic_risk.early_warning.compute_early_warning`)
    is *elevated* in pre-event windows preceding banking-crisis dates
    compared to null windows drawn from the same series at safe
    distance from any event.

Decision rule (pre-registered, written *before* any data is run)::

    For each crisis c with a valid pre-event window:
        AUC_c          = ROC AUC of (pre-event scores vs null-window scores)
        AUC_c (95% CI) = percentile bootstrap, n=10000 stratified resamples
        p_c            = one-sided permutation p (alternative: pre > null)

    Across crises:
        p_BONF = Bonferroni-corrected p-values (k = number of valid crises)

    HARD_FAIL : ∃ c with AUC_c <= ``fail_auc`` (default 0.55)
                OR ∃ c with auc_ci_low <= 0.5 + ``ci_floor_tol`` (CI crosses 0.5)
                → archive negative; close the hypothesis.
    HARD_PASS : >= 2 crises with auc_ci_low >= ``pass_auc_ci_low``
                AND p_BONF_c <= ``pass_alpha`` (defaults 0.70, 0.01).
    UNDECIDED : neither — collect more data, do not promote tier.

Bonferroni replaces the v1 Benjamini-Hochberg FDR control: the user
prefers strict family-wise error control given the small number of
crises and the high cost of a false MEASURED promotion.

Pure-function API. No I/O. Determinism via explicit ``seed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .event_ledger import BankingCrisisEvent, BankingCrisisLedger

__all__ = [
    "FalsificationConfig",
    "CrisisOutcome",
    "FalsificationReport",
    "auc_mann_whitney",
    "auc_bootstrap_ci",
    "bonferroni_correction",
    "run_falsification",
    "run_score_level_falsification",
    "run_end_to_end_falsification",
]


Verdict = Literal["HARD_FAIL", "HARD_PASS", "UNDECIDED"]


# ---------------------------------------------------------------------------
# Statistics primitives
# ---------------------------------------------------------------------------


def auc_mann_whitney(positives: NDArray[np.float64], negatives: NDArray[np.float64]) -> float:
    """ROC AUC via the Mann-Whitney U statistic.

    AUC = P(X_pos > X_neg) + 0.5 * P(X_pos == X_neg).
    Returns 0.5 when either array is empty.
    """
    if positives.size == 0 or negatives.size == 0:
        return 0.5
    pos = positives[np.isfinite(positives)]
    neg = negatives[np.isfinite(negatives)]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    combined = np.concatenate([pos, neg])
    _, inv, counts = np.unique(combined, return_inverse=True, return_counts=True)
    raw_ranks = combined.argsort().argsort().astype(np.float64) + 1.0
    sums = np.bincount(inv, weights=raw_ranks)
    avg = sums / counts
    ranks_avg = avg[inv]
    rank_sum_pos = float(ranks_avg[: pos.size].sum())
    n_pos = pos.size
    n_neg = neg.size
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def auc_bootstrap_ci(
    positives: NDArray[np.float64],
    negatives: NDArray[np.float64],
    *,
    n_bootstrap: int = 10000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Stratified percentile-bootstrap CI on the AUC.

    Resamples positives and negatives independently *with replacement*
    ``n_bootstrap`` times, computes the AUC on each resample, and
    returns ``(point_estimate, ci_low, ci_high)`` where the CI is the
    central ``confidence`` percentile interval. Stratified resampling
    preserves the marginal sample sizes — an AUC artefact of mixing
    the two arms is impossible.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be >= 1, got {n_bootstrap}")
    pos = positives[np.isfinite(positives)]
    neg = negatives[np.isfinite(negatives)]
    point = auc_mann_whitney(pos, neg)
    if pos.size < 2 or neg.size < 2:
        return point, point, point
    rng = np.random.default_rng(seed)
    samples = np.empty(n_bootstrap, dtype=np.float64)
    n_pos = pos.size
    n_neg = neg.size
    for b in range(n_bootstrap):
        idx_p = rng.integers(0, n_pos, size=n_pos)
        idx_n = rng.integers(0, n_neg, size=n_neg)
        samples[b] = auc_mann_whitney(pos[idx_p], neg[idx_n])
    alpha = (1.0 - confidence) / 2.0
    ci_low = float(np.quantile(samples, alpha))
    ci_high = float(np.quantile(samples, 1.0 - alpha))
    return point, ci_low, ci_high


def _permutation_p(
    positives: NDArray[np.float64],
    negatives: NDArray[np.float64],
    *,
    n_permutations: int,
    rng: np.random.Generator,
) -> float:
    """One-sided permutation p-value: P(AUC_perm >= AUC_observed | exchangeable)."""
    pos = positives[np.isfinite(positives)]
    neg = negatives[np.isfinite(negatives)]
    if pos.size == 0 or neg.size == 0:
        return 1.0
    observed = auc_mann_whitney(pos, neg)
    pool = np.concatenate([pos, neg])
    n_pos = pos.size
    exceedances = 0
    for _ in range(n_permutations):
        perm = rng.permutation(pool)
        a = auc_mann_whitney(perm[:n_pos], perm[n_pos:])
        if a >= observed:
            exceedances += 1
    return float((exceedances + 1) / (n_permutations + 1))


def bonferroni_correction(p_values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Family-wise error-rate control via Bonferroni: ``p_adj = min(1, m * p)``.

    Order is preserved relative to the input. More conservative than
    Benjamini-Hochberg FDR — chosen here per the v2 protocol because
    promoting C-SYSRISK-PHASE to MEASURED on a false positive is
    treated as catastrophic.
    """
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1:
        raise ValueError(f"p_values must be 1-D, got shape={p.shape}")
    if p.size == 0:
        return p.copy()
    if np.any(p < 0) or np.any(p > 1) or not np.isfinite(p).all():
        raise ValueError("p_values must be finite values in [0, 1]")
    m = p.size
    return np.clip(p * m, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Window-extraction helpers
# ---------------------------------------------------------------------------


def _date_to_index(target: date, dates: tuple[date, ...]) -> int | None:
    out: int | None = None
    for i, d in enumerate(dates):
        if d <= target:
            out = i
        else:
            break
    return out


def _pre_event_window(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    event_start: date,
    window_days: int,
) -> NDArray[np.float64]:
    end_idx = _date_to_index(event_start - timedelta(days=1), dates)
    if end_idx is None:
        return np.empty(0, dtype=np.float64)
    start_idx = max(0, end_idx - window_days + 1)
    return score[start_idx : end_idx + 1]


def _null_windows(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    window_days: int,
    min_distance_days: int,
    rng: np.random.Generator,
    n_windows: int,
    country_filter: str | None,
) -> NDArray[np.float64]:
    if score.size != len(dates):
        raise ValueError(f"score length {score.size} != dates length {len(dates)}")
    if score.size < window_days:
        return np.empty(0, dtype=np.float64)
    relevant_events: tuple[BankingCrisisEvent, ...]
    if country_filter is None:
        relevant_events = ledger.events
    else:
        relevant_events = ledger.by_country(country_filter)

    def _too_close(window_end_idx: int) -> bool:
        window_start_date = dates[window_end_idx - window_days + 1]
        window_end_date = dates[window_end_idx]
        for ev in relevant_events:
            buffer = timedelta(days=min_distance_days)
            ev_lo = ev.start - buffer
            ev_hi = ev.end + buffer
            if not (window_end_date < ev_lo or window_start_date > ev_hi):
                return True
        return False

    valid_ends: list[int] = []
    for end_idx in range(window_days - 1, score.size):
        if not _too_close(end_idx):
            valid_ends.append(end_idx)
    if not valid_ends:
        return np.empty(0, dtype=np.float64)
    take = min(n_windows, len(valid_ends))
    chosen = rng.choice(np.asarray(valid_ends, dtype=np.int64), size=take, replace=False)
    flat = np.concatenate([score[int(c) - window_days + 1 : int(c) + 1] for c in chosen])
    return flat


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FalsificationConfig:
    """Pre-registered falsification protocol (v2).

    Attributes
    ----------
    pre_event_window_days
        Length of the pre-event window in days (default 60).
    null_window_count
        Number of null windows to draw per run (default 30).
    min_distance_from_event_days
        Buffer between any null window and any event interval
        (default 365).
    n_permutations
        Permutations for the AUC p-value (default 5000).
    n_bootstrap
        Stratified-bootstrap resamples for the AUC CI (default 10000).
    confidence
        Confidence level for the AUC CI (default 0.95).
    fail_auc
        Hard-fail threshold on the *point* AUC (default 0.55).
    ci_floor_tol
        Tolerance above 0.5 below which the CI lower bound triggers
        HARD_FAIL (default 0.0 — strict: any CI crossing 0.5 fails).
    pass_auc_ci_low
        HARD_PASS threshold on the AUC *CI lower bound* (default 0.70).
        Stronger than v1's point-estimate threshold: requires the
        whole CI to clear the bar.
    pass_alpha
        HARD_PASS Bonferroni-adjusted p threshold (default 0.01).
    seed
        Deterministic RNG seed (default 42).
    """

    pre_event_window_days: int = 60
    null_window_count: int = 30
    min_distance_from_event_days: int = 365
    n_permutations: int = 5000
    n_bootstrap: int = 10000
    confidence: float = 0.95
    fail_auc: float = 0.55
    ci_floor_tol: float = 0.0
    pass_auc_ci_low: float = 0.70
    pass_alpha: float = 0.01
    seed: int = 42

    def __post_init__(self) -> None:
        if self.pre_event_window_days < 4:
            raise ValueError(
                f"pre_event_window_days must be >= 4, got {self.pre_event_window_days}"
            )
        if self.null_window_count < 2:
            raise ValueError(f"null_window_count must be >= 2, got {self.null_window_count}")
        if self.min_distance_from_event_days < 0:
            raise ValueError(
                f"min_distance_from_event_days must be >= 0, "
                f"got {self.min_distance_from_event_days}"
            )
        if self.n_permutations < 100:
            raise ValueError(f"n_permutations must be >= 100, got {self.n_permutations}")
        if self.n_bootstrap < 100:
            raise ValueError(f"n_bootstrap must be >= 100, got {self.n_bootstrap}")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError(f"confidence must be in (0, 1), got {self.confidence}")
        if not 0.0 < self.fail_auc < self.pass_auc_ci_low <= 1.0:
            raise ValueError(
                f"thresholds must satisfy 0 < fail_auc < pass_auc_ci_low <= 1; "
                f"got fail={self.fail_auc}, pass={self.pass_auc_ci_low}"
            )
        if self.ci_floor_tol < 0:
            raise ValueError(f"ci_floor_tol must be >= 0, got {self.ci_floor_tol}")
        if not 0.0 < self.pass_alpha <= 0.1:
            raise ValueError(f"pass_alpha must be in (0, 0.1], got {self.pass_alpha}")


@dataclass(frozen=True, slots=True)
class CrisisOutcome:
    """Per-crisis outcome of the falsification run (v2)."""

    label: str
    country: str
    event_start: date
    n_pre_event: int
    n_null: int
    auc: float
    auc_ci_low: float
    auc_ci_high: float
    p_value: float
    p_bonferroni: float


@dataclass(frozen=True, slots=True)
class FalsificationReport:
    """Top-level falsification verdict + per-crisis evidence."""

    outcomes: tuple[CrisisOutcome, ...]
    verdict: Verdict
    config: FalsificationConfig


def run_falsification(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    config: FalsificationConfig | None = None,
    country_filter: str | None = None,
) -> FalsificationReport:
    """Run the pre-registered v2 falsification battery.

    Parameters
    ----------
    score
        Time-resolved early-warning score, shape ``(T,)``.
    dates
        Length-``T`` tuple of calendar dates, monotonically increasing.
    ledger
        :class:`BankingCrisisLedger` of crisis events.
    config
        Optional :class:`FalsificationConfig`; defaults to the v2
        pre-registered settings.
    country_filter
        Optional ISO-3 country code to restrict events and null
        masking to a single jurisdiction.
    """
    cfg = config if config is not None else FalsificationConfig()
    s = np.asarray(score, dtype=np.float64)
    if s.ndim != 1:
        raise ValueError(f"score must be 1-D, got shape={s.shape}")
    if s.size != len(dates):
        raise ValueError(f"score length {s.size} != dates length {len(dates)}")
    for i in range(1, len(dates)):
        if dates[i] <= dates[i - 1]:
            raise ValueError(
                f"dates must be strictly increasing; "
                f"dates[{i - 1}]={dates[i - 1]} >= dates[{i}]={dates[i]}"
            )

    rng = np.random.default_rng(cfg.seed)
    if country_filter is None:
        candidate_events = ledger.events
    else:
        candidate_events = ledger.by_country(country_filter)

    outcomes_in_order: list[CrisisOutcome] = []
    p_per_crisis: list[float] = []

    for ev in candidate_events:
        pre = _pre_event_window(s, dates, ev.start, cfg.pre_event_window_days)
        pre = pre[np.isfinite(pre)]
        if pre.size < 4:
            continue
        nulls = _null_windows(
            s,
            dates,
            ledger,
            window_days=cfg.pre_event_window_days,
            min_distance_days=cfg.min_distance_from_event_days,
            rng=rng,
            n_windows=cfg.null_window_count,
            country_filter=country_filter,
        )
        nulls = nulls[np.isfinite(nulls)]
        if nulls.size < 4:
            continue
        point, ci_low, ci_high = auc_bootstrap_ci(
            pre,
            nulls,
            n_bootstrap=cfg.n_bootstrap,
            seed=cfg.seed,
            confidence=cfg.confidence,
        )
        p = _permutation_p(pre, nulls, n_permutations=cfg.n_permutations, rng=rng)
        outcomes_in_order.append(
            CrisisOutcome(
                label=ev.label,
                country=ev.country,
                event_start=ev.start,
                n_pre_event=int(pre.size),
                n_null=int(nulls.size),
                auc=point,
                auc_ci_low=ci_low,
                auc_ci_high=ci_high,
                p_value=p,
                p_bonferroni=float("nan"),
            )
        )
        p_per_crisis.append(p)

    if not outcomes_in_order:
        return FalsificationReport(outcomes=tuple(), verdict="UNDECIDED", config=cfg)

    p_bonf = bonferroni_correction(np.asarray(p_per_crisis, dtype=np.float64))
    finalised = tuple(
        CrisisOutcome(
            label=o.label,
            country=o.country,
            event_start=o.event_start,
            n_pre_event=o.n_pre_event,
            n_null=o.n_null,
            auc=o.auc,
            auc_ci_low=o.auc_ci_low,
            auc_ci_high=o.auc_ci_high,
            p_value=o.p_value,
            p_bonferroni=float(p_bonf[i]),
        )
        for i, o in enumerate(outcomes_in_order)
    )

    ci_floor = 0.5 + cfg.ci_floor_tol
    if any(o.auc <= cfg.fail_auc or o.auc_ci_low <= ci_floor for o in finalised):
        verdict: Verdict = "HARD_FAIL"
    else:
        passing = [
            o
            for o in finalised
            if o.auc_ci_low >= cfg.pass_auc_ci_low and o.p_bonferroni <= cfg.pass_alpha
        ]
        verdict = "HARD_PASS" if len(passing) >= 2 else "UNDECIDED"

    return FalsificationReport(outcomes=finalised, verdict=verdict, config=cfg)


# ---------------------------------------------------------------------------
# Scope-explicit aliases — make the validation boundary auditable
# ---------------------------------------------------------------------------


def run_score_level_falsification(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    config: FalsificationConfig | None = None,
    country_filter: str | None = None,
) -> FalsificationReport:
    """Score-level alias of :func:`run_falsification` — explicit scope tag.

    Identical behaviour to :func:`run_falsification`. The dedicated
    name makes the *scope* of the test auditable in caller code:
    this function evaluates a pre-computed score series; it does
    NOT validate the upstream pipeline that produced the score.
    For end-to-end (exposure → verdict) validation see
    :func:`run_end_to_end_falsification`.
    """
    return run_falsification(score, dates, ledger, config=config, country_filter=country_filter)


def run_end_to_end_falsification(
    *args: object,
    **kwargs: object,
) -> FalsificationReport:
    """End-to-end falsification — NOT YET IMPLEMENTED.

    The full pipeline — temporal exposure panel → topology →
    coupling → Kuramoto dynamics → r(t) → early-warning score →
    crisis verdict — requires real-data ingest and an executable
    null-audit orchestrator, neither of which has landed on
    ``main`` (see ``LIMITATIONS.md`` § "Domain limitations" and
    ``null_models.py`` module docstring).

    Calling this function fails-closed via
    :class:`NotImplementedError` rather than running a partial
    pipeline that could be misread as end-to-end evidence.
    """
    raise NotImplementedError(
        "End-to-end falsification (exposure panel → verdict) is not "
        "yet implemented on main. The composed null-audit orchestrator "
        "and temporal-exposure ingest are both deferred — see "
        "research/systemic_risk/LIMITATIONS.md and PROTOCOL.md § 4. "
        "For score-level evaluation use run_score_level_falsification."
    )
