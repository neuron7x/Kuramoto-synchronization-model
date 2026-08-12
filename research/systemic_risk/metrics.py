# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Detection-side metrics — precision / recall / FPR / FNR / lead-time.

§ 14 of the canonical R&D checklist forbids AUC-only reporting.
This module ships the conventional confusion-matrix metrics plus
a strict pre-event-window lead-time aggregator. Every undefined
denominator yields NaN — never silently zero — to refuse fake
quality on empty input.

Pure-function API. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ClassificationMetrics",
    "LeadTimeConfig",
    "LeadTimeMetrics",
    "compute_classification_metrics",
    "compute_lead_time_metrics",
]


@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    """Confusion-matrix-derived metrics.

    NaN policy (per § 8 of the agent calibration spec):

    * ``precision``  → NaN when ``tp + fp == 0`` (no predictions).
    * ``recall``     → NaN when ``tp + fn == 0`` (no positives).
    * ``false_positive_rate``  → NaN when ``fp + tn == 0``.
    * ``false_negative_rate``  → NaN when ``fn + tp == 0``.

    NaN, not 0.0 — the absence of denominators must propagate.
    """

    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float


def _coerce_binary_or_bool(name: str, arr: NDArray[np.generic]) -> NDArray[np.bool_]:
    """Accept ``bool`` or strictly-binary ``{0, 1}`` integer arrays.

    Refuses arbitrary numeric input — silent ``np.asarray(..., dtype=bool)``
    casting would map ``-1``, ``2``, ``np.nan`` all to ``True`` and
    smuggle a graded score through a binary contract. Fail-closed.
    """
    raw = np.asarray(arr)
    if raw.dtype == np.bool_:
        return raw
    if not np.issubdtype(raw.dtype, np.integer):
        raise ValueError(
            f"{name} must be bool or binary {{0, 1}} integer array; got dtype={raw.dtype}"
        )
    if not np.isin(raw, np.array([0, 1])).all():
        raise ValueError(
            f"{name} must contain only 0/1 values when not bool; got values outside {{0, 1}}"
        )
    return raw.astype(np.bool_)


def compute_classification_metrics(
    y_true: NDArray[np.generic],
    y_pred: NDArray[np.generic],
) -> ClassificationMetrics:
    """Confusion-matrix metrics from boolean / binary 0-1 truth and prediction arrays.

    Inputs must be either ``bool`` or strictly-binary ``{0, 1}``
    integer arrays; arbitrary numeric input is rejected to prevent
    silent coercion of graded scores into a binary contract.
    """
    t = _coerce_binary_or_bool("y_true", y_true)
    p = _coerce_binary_or_bool("y_pred", y_pred)
    if t.shape != p.shape or t.ndim != 1:
        raise ValueError(
            f"y_true and y_pred must be 1-D with matching shape; "
            f"got y_true={t.shape}, y_pred={p.shape}"
        )
    tp = int(np.logical_and(t, p).sum())
    fp = int(np.logical_and(~t, p).sum())
    tn = int(np.logical_and(~t, ~p).sum())
    fn = int(np.logical_and(t, ~p).sum())
    pred_pos = tp + fp
    cond_pos = tp + fn
    cond_neg = fp + tn
    precision = float(tp / pred_pos) if pred_pos > 0 else float("nan")
    recall = float(tp / cond_pos) if cond_pos > 0 else float("nan")
    fpr = float(fp / cond_neg) if cond_neg > 0 else float("nan")
    fnr = float(fn / cond_pos) if cond_pos > 0 else float("nan")
    return ClassificationMetrics(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=precision,
        recall=recall,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
    )


@dataclass(frozen=True, slots=True)
class LeadTimeConfig:
    """Pre-registered lead-time parameters.

    A signal counts as a *valid early warning* iff it fires inside
    the pre-event window ``[event - max_lead_days, event - min_lead_days]``.
    Signals on or after the event date never count
    (post-event contamination is a hard fail).

    Attributes
    ----------
    min_lead_days
        Minimum gap (days) between alarm and event for the alarm
        to count. ``min_lead_days = 1`` excludes same-day signals.
        ``min_lead_days = 0`` includes same-day signals — discouraged
        for pre-event detection but supported for completeness.
    max_lead_days
        Maximum gap (days). The pre-event window is closed at
        both ends; an alarm older than ``max_lead_days`` does not
        count as a warning *for this event*.

    Notes
    -----
    Post-event masking is enforced *by construction* — the
    aggregator considers only dates strictly before each event
    (or on it when ``min_lead_days == 0``). A separate
    ``event_exclusion_days_after`` parameter would belong to
    label-construction or evaluation-window masking, not to the
    lead-time aggregator; it has been deliberately removed from
    this dataclass to avoid a decorative API.
    """

    min_lead_days: int
    max_lead_days: int

    def __post_init__(self) -> None:
        if self.min_lead_days < 0:
            raise ValueError(f"min_lead_days must be >= 0, got {self.min_lead_days}")
        if self.max_lead_days < self.min_lead_days:
            raise ValueError(
                f"max_lead_days ({self.max_lead_days}) must be >= "
                f"min_lead_days ({self.min_lead_days})"
            )
        if self.max_lead_days < 1:
            raise ValueError(f"max_lead_days must be >= 1, got {self.max_lead_days}")


@dataclass(frozen=True, slots=True)
class LeadTimeMetrics:
    """Aggregate lead-time profile across a set of events."""

    event_count: int
    detected_event_count: int
    lead_times: tuple[int, ...]
    median_lead_time: float
    min_lead_time: int | None
    max_lead_time: int | None


def _first_valid_lead(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    *,
    threshold: float,
    event_start: date,
    config: LeadTimeConfig,
) -> int | None:
    """Return the earliest valid pre-event lead time in days, or None."""
    s = np.asarray(score, dtype=np.float64)
    if s.shape != (len(dates),):
        raise ValueError(f"score length {s.size} != dates length {len(dates)}")
    window_lo = event_start - timedelta(days=config.max_lead_days)
    window_hi = event_start - timedelta(days=config.min_lead_days)
    # Iterate in chronological order; first match is the earliest
    # valid pre-event alarm — aligns with the "use first valid signal"
    # contract.
    for i, d in enumerate(dates):
        if d < window_lo:
            continue
        if d > window_hi:
            break
        if not np.isfinite(s[i]):
            continue
        if s[i] >= threshold:
            return int((event_start - d).days)
    return None


def compute_lead_time_metrics(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    *,
    threshold: float,
    event_dates: tuple[date, ...],
    config: LeadTimeConfig,
    allow_warmup_nan: bool = True,
) -> LeadTimeMetrics:
    """Aggregate lead-time profile across a set of pre-registered events.

    ``event_dates`` is the canonical labelled set; dates outside
    ``dates`` (or with no valid pre-event window inside the score
    range) count as *undetected* events. Same-day and post-event
    alarms never count regardless of how high they spike.

    ``allow_warmup_nan`` (default ``True``) tolerates leading NaN
    values in ``score`` arising from rolling-window warmup; any
    Inf or NaN past warmup still raises. Set to ``False`` to
    enforce strict finiteness on the entire series.

    Fail-closed
    -----------
    * ``threshold`` not finite → :class:`ValueError`
    * ``dates`` not strictly increasing → :class:`ValueError`
    * ``score`` length ≠ ``len(dates)`` → :class:`ValueError`
    * non-finite ``score`` outside the leading warmup band when
      ``allow_warmup_nan=True`` (or anywhere when ``False``)
      → :class:`ValueError`
    """
    if not np.isfinite(threshold):
        raise ValueError(f"threshold must be finite, got {threshold}")
    if config.min_lead_days < 0 or config.max_lead_days < 1:
        raise ValueError("LeadTimeConfig invariants must already be satisfied")
    if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
        raise ValueError("dates must be strictly increasing")
    s = np.asarray(score, dtype=np.float64)
    if s.shape != (len(dates),):
        raise ValueError(f"score length {s.size} != dates length {len(dates)}")
    if allow_warmup_nan:
        # Allow only a leading contiguous block of NaN (rolling-warmup);
        # any NaN/Inf past the first finite value is a hard fail.
        finite = np.isfinite(s)
        if finite.any():
            first_finite = int(np.argmax(finite))
            tail = s[first_finite:]
            if not np.isfinite(tail).all():
                raise ValueError(
                    "score contains NaN/Inf past the leading warmup band; "
                    "set allow_warmup_nan=False to inspect, or fix the score"
                )
    else:
        if not np.isfinite(s).all():
            raise ValueError("score must be finite when allow_warmup_nan=False")
    leads: list[int] = []
    for ev in event_dates:
        lead = _first_valid_lead(
            score,
            dates,
            threshold=threshold,
            event_start=ev,
            config=config,
        )
        if lead is not None:
            leads.append(lead)
    n_events = len(event_dates)
    n_detected = len(leads)
    median_lt = float(np.median(leads)) if leads else float("nan")
    return LeadTimeMetrics(
        event_count=n_events,
        detected_event_count=n_detected,
        lead_times=tuple(sorted(leads)),
        median_lead_time=median_lt,
        min_lead_time=min(leads) if leads else None,
        max_lead_time=max(leads) if leads else None,
    )
