# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Leakage / causality sentinel — six runnable checks.

Operationalises § 5 of the canonical-7 charter. Each forbidden
time-flow pattern in the user's draft is paired with a runnable
predicate; the sentinel's :func:`run_leakage_audit` aggregates the
six per-check results into a single Boolean ``detected`` flag.
Any single ``detected = True`` halts the pipeline (charter § 1
trigger T2 → INVALIDATE).

Six sentinels:

1. **future_data** — score-construction must depend only on
   observations whose timestamp ≤ the score-emit timestamp.
   Verified by future-segment mutation: mutate values past a
   chosen index, recompute the score, assert the prefix is
   bit-identical. Already enforced for CSD by
   ``test_critical_slowing_down.test_no_lookahead_leakage``;
   reused here as a generic helper.
2. **post_event_contamination** — every alarm at or after the
   event date contributes 0 to the lead-time aggregator. The
   sentinel inspects a ``LeadTimeMetrics``-shaped object and
   asserts ``min_lead_time >= 1`` (or ``None`` for no detection).
3. **centered_windows** — pre-registered config dict is scanned
   for forbidden flags (``center=True``, ``align="center"``,
   ``offset != 0`` for trailing operations).
4. **full_sample_normalisation** — a structured op-log is scanned
   for any ``mean``/``std``/``zscore``/``minmax`` operation
   called over the *full* series before train/test split.
5. **label_leakage** — the score-construction op-graph (caller-
   supplied DAG of ``(op_name, time_in, time_out)``) is scanned
   for any edge where ``time_in > time_out``.
6. **crisis_date_tuning** — pre-registration timestamp must
   strictly precede the timestamp of the first AUC evaluation.

Pure-function API. No I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "LeakageType",
    "LeakageOutcome",
    "LeakageReport",
    "LeadTimeMetricsLike",
    "OpRecord",
    "check_future_data_via_mutation",
    "check_post_event_contamination",
    "check_centered_windows",
    "check_full_sample_normalisation",
    "check_label_leakage",
    "check_crisis_date_tuning",
    "run_leakage_audit",
]


LeakageType = Literal[
    "future_data",
    "post_event_contamination",
    "centered_windows",
    "full_sample_normalisation",
    "label_leakage",
    "crisis_date_tuning",
]


_FORBIDDEN_CENTERED_KEYS: frozenset[str] = frozenset(
    {"center", "align_center", "centered_window", "two_sided_window"}
)
_FORBIDDEN_FULL_SAMPLE_OPS: frozenset[str] = frozenset(
    {
        "full_sample_mean",
        "full_sample_std",
        "full_sample_zscore",
        "full_sample_minmax",
        "full_series_norm",
    }
)


@dataclass(frozen=True, slots=True)
class LeakageOutcome:
    """One sentinel's evaluation."""

    type: LeakageType
    detected: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LeakageReport:
    """Aggregate report from the full audit."""

    outcomes: tuple[LeakageOutcome, ...]
    detected: bool


class LeadTimeMetricsLike(Protocol):
    """Anything with the lead-time aggregator's surface."""

    detected_event_count: int
    min_lead_time: int | None


@dataclass(frozen=True, slots=True)
class OpRecord:
    """One node in the score-construction op-graph.

    Attributes
    ----------
    op_name
        Operation identifier (e.g. ``"rolling_mean"``).
    time_in_index
        Index of the latest observation the op consumed.
    time_out_index
        Index at which the op emitted its result.
    """

    op_name: str
    time_in_index: int
    time_out_index: int


# ---------------------------------------------------------------------------
# 1. future_data — mutate-future regression
# ---------------------------------------------------------------------------


def check_future_data_via_mutation(
    score_builder: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    *,
    base_series: NDArray[np.float64],
    cut_index: int,
    perturbation: float = 1e6,
) -> LeakageOutcome:
    """Run the future-segment-mutation invariant on a score builder.

    The contract: ``score_builder(x)[: cut_index]`` must equal
    ``score_builder(x_with_future_mutated)[: cut_index]`` exactly
    (modulo NaN matching), because the prefix cannot legally
    depend on values beyond ``cut_index``.

    A failure is registered when *any* prefix index differs,
    accounting for NaN as equal-to-itself in this comparison.
    """
    if base_series.ndim != 1:
        raise ValueError(f"base_series must be 1-D, got shape={base_series.shape}")
    if not 0 < cut_index < base_series.size:
        raise ValueError(
            f"cut_index must satisfy 0 < cut_index < n={base_series.size}, got {cut_index}"
        )
    base = score_builder(base_series.copy())
    mutated = base_series.copy()
    mutated[cut_index:] = perturbation
    after = score_builder(mutated)
    prefix_base = base[:cut_index]
    prefix_after = after[:cut_index]
    # NaN-tolerant equality.
    same_nan = np.logical_and(np.isnan(prefix_base), np.isnan(prefix_after))
    same_val = prefix_base == prefix_after
    matched = bool(np.all(np.logical_or(same_nan, same_val)))
    return LeakageOutcome(
        type="future_data",
        detected=not matched,
        reason=(
            "prefix differs after future-segment mutation — score builder reads future values"
            if not matched
            else "prefix bit-identical under future-segment mutation"
        ),
    )


# ---------------------------------------------------------------------------
# 2. post_event_contamination — lead-time aggregator must reject same-day+
# ---------------------------------------------------------------------------


def check_post_event_contamination(
    metrics: LeadTimeMetricsLike,
    *,
    min_required_lead_days: int = 1,
) -> LeakageOutcome:
    """Inspect a lead-time metrics object for post-event signals.

    ``min_lead_time`` must be either ``None`` (no detection at
    all) or ``>= min_required_lead_days``; anything smaller would
    mean an alarm fired on or after the event day, which counts
    as post-event contamination under the strict pre-event-only
    contract.
    """
    lead = metrics.min_lead_time
    if lead is None:
        return LeakageOutcome(
            type="post_event_contamination",
            detected=False,
            reason="no detections — no contamination by construction",
        )
    if lead < min_required_lead_days:
        return LeakageOutcome(
            type="post_event_contamination",
            detected=True,
            reason=(
                f"min lead-time {lead}d < required {min_required_lead_days}d — "
                "post-event signal counted as detection"
            ),
        )
    return LeakageOutcome(
        type="post_event_contamination",
        detected=False,
        reason=f"min lead-time {lead}d clears required {min_required_lead_days}d",
    )


# ---------------------------------------------------------------------------
# 3. centered_windows — config-flag scan
# ---------------------------------------------------------------------------


def check_centered_windows(
    config: Mapping[str, Any],
) -> LeakageOutcome:
    """Scan a config mapping for forbidden centred-window flags."""
    matches = sorted(k for k in config if k in _FORBIDDEN_CENTERED_KEYS and config[k])
    # Also catch ``align == "center"`` / ``"centred"``.
    align = config.get("align")
    if isinstance(align, str) and align.lower() in {"center", "centre", "centred"}:
        matches.append(f"align={align!r}")
    if "offset" in config and isinstance(config["offset"], (int, float)):
        if config["offset"] > 0:
            matches.append(f"offset={config['offset']}")
    if matches:
        return LeakageOutcome(
            type="centered_windows",
            detected=True,
            reason=f"forbidden centred-window flags: {matches}",
        )
    return LeakageOutcome(
        type="centered_windows",
        detected=False,
        reason="no centred-window flags in config",
    )


# ---------------------------------------------------------------------------
# 4. full_sample_normalisation — op-log scan
# ---------------------------------------------------------------------------


def check_full_sample_normalisation(
    op_log: Sequence[str],
) -> LeakageOutcome:
    """Detect any forbidden full-sample normalisation operation."""
    matches = sorted({op for op in op_log if op in _FORBIDDEN_FULL_SAMPLE_OPS})
    if matches:
        return LeakageOutcome(
            type="full_sample_normalisation",
            detected=True,
            reason=f"forbidden full-sample ops: {matches}",
        )
    return LeakageOutcome(
        type="full_sample_normalisation",
        detected=False,
        reason="no full-sample normalisation in op-log",
    )


# ---------------------------------------------------------------------------
# 5. label_leakage — DAG check on the op-graph
# ---------------------------------------------------------------------------


def check_label_leakage(
    op_graph: Sequence[OpRecord],
) -> LeakageOutcome:
    """Detect any op that consumed a future-time input.

    The contract: for every record, ``time_in_index <= time_out_index``.
    A backwards edge is the explicit signature of label leakage.
    """
    violators = [rec for rec in op_graph if rec.time_in_index > rec.time_out_index]
    if violators:
        names = sorted({v.op_name for v in violators})
        return LeakageOutcome(
            type="label_leakage",
            detected=True,
            reason=f"backwards edges in op-graph: {names}",
        )
    return LeakageOutcome(
        type="label_leakage",
        detected=False,
        reason="op-graph has no backwards edges",
    )


# ---------------------------------------------------------------------------
# 6. crisis_date_tuning — pre-registration timestamp check
# ---------------------------------------------------------------------------


def check_crisis_date_tuning(
    *,
    crisis_lock_timestamp_utc: str,
    first_evaluation_timestamp_utc: str,
) -> LeakageOutcome:
    """Pre-registration timestamp must strictly precede first evaluation."""
    try:
        lock = datetime.fromisoformat(crisis_lock_timestamp_utc)
        first_eval = datetime.fromisoformat(first_evaluation_timestamp_utc)
    except ValueError as exc:
        return LeakageOutcome(
            type="crisis_date_tuning",
            detected=True,
            reason=f"timestamp parse error: {exc}",
        )
    if lock >= first_eval:
        return LeakageOutcome(
            type="crisis_date_tuning",
            detected=True,
            reason=(
                f"crisis-date lock {lock.isoformat()} not strictly before "
                f"first evaluation {first_eval.isoformat()} — tuning suspected"
            ),
        )
    return LeakageOutcome(
        type="crisis_date_tuning",
        detected=False,
        reason=(f"lock {lock.isoformat()} strictly precedes first eval {first_eval.isoformat()}"),
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def run_leakage_audit(
    outcomes: Sequence[LeakageOutcome],
) -> LeakageReport:
    """Compose individual sentinel outcomes into a single report."""
    detected = any(o.detected for o in outcomes)
    return LeakageReport(outcomes=tuple(outcomes), detected=detected)
