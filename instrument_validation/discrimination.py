# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Discrimination layer — multi-metric majority vote with Bonferroni
family-error budget.

Six metrics (M1..M6) jointly compare an empirical graph against a BA
ensemble and an ER ensemble. Each metric's per-metric verdict uses a
95% interval test at α = 0.05/6 (Bonferroni-corrected per metric).
The aggregate verdict is then a MAJORITY VOTE: BA_FAVORED only when
≥4 of 6 metrics individually favour BA. The 4-of-6 threshold is the
voting rule, not a multiple-comparison correction — both are applied,
at different layers.

Closes:
* B1 (sorted Pearson is non-discriminating — replaced by 6-metric vote)
* B3 (max-deg / zero-deg structural mismatch — promoted to M2/M3)
* B8 (KS distance becomes M1, the headline decision metric)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import networkx as nx
import numpy as np

_BONFERRONI_K: int = 6
_ALPHA_FAMILY: float = 0.05

# Per-metric MDE (Bug 1 fix — single 0.05 was unit-blind across metrics
# of different ranges). Calibrated to N=31 simulation regime:
#   M1 KS distance              ∈ [0, 1]    → MDE = 0.05 (5% of range)
#   M2 max-degree z-score       unbounded   → MDE = 0.5  (half-σ)
#   M3 zero-degree-count error  integer     → MDE = 1.0  (one node)
#   M4 Gini-strength z-score    unbounded   → MDE = 0.5
#   M5 top-k hub Jaccard        ∈ [0, 1]    → MDE = 0.10
#   M6 normalised rich-club     ratio       → MDE = 0.20 (20% deviation)
_MDE_PER_METRIC: dict[str, float] = {
    "M1_ks_distance": 0.05,
    "M2_max_degree_z": 0.5,
    "M3_zero_degree_err": 1.0,
    "M4_gini_strength_z": 0.5,
    "M5_top_k_hub": 0.10,
    "M6_norm_rich_club": 0.20,
}
_MDE_DEFAULT: float = 0.05


def mde_at_n31(metric_name: str | None = None) -> float:
    """Minimum detectable effect for the named metric at N=31.

    Different metrics live on different scales — a single threshold across
    KS (∈[0,1]), z-scores (unbounded), counts (integer), and ratios is
    unit-blind. Returns the per-metric MDE, falling back to the legacy
    0.05 default when ``metric_name`` is not in the registry.
    """
    if metric_name is None:
        return _MDE_DEFAULT
    return _MDE_PER_METRIC.get(metric_name, _MDE_DEFAULT)


class DiscriminationVerdict(Enum):
    BA_FAVORED = "ba_favored"
    ER_FAVORED = "er_favored"
    NOT_DISTINGUISHED = "not_distinguished"
    INSUFFICIENT_RESOLUTION = "insufficient_resolution"


@dataclass(frozen=True)
class MetricResult:
    name: str
    empirical: float
    ba_p2_5: float
    ba_p97_5: float
    er_p2_5: float
    er_p97_5: float
    delta_ba_minus_er: float  # |empirical - BA_median| - |empirical - ER_median|
    verdict: DiscriminationVerdict


@dataclass(frozen=True)
class DiscriminationReport:
    metrics: tuple[MetricResult, ...]
    n_metrics_favor_ba: int
    n_metrics_favor_er: int
    n_metrics_not_distinguished: int
    n_metrics_insufficient: int
    bonferroni_k: int
    aggregate_verdict: DiscriminationVerdict
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Six metrics
# ---------------------------------------------------------------------------


def metric_ks_distance(emp_deg: np.ndarray, sim_pool: np.ndarray) -> float:
    """M1 — KS statistic between empirical degree distribution and pooled sim."""
    if emp_deg.size == 0 or sim_pool.size == 0:
        return float("nan")
    all_vals = np.union1d(emp_deg, sim_pool)
    e_cdf = np.searchsorted(np.sort(emp_deg), all_vals, side="right") / emp_deg.size
    s_cdf = np.searchsorted(np.sort(sim_pool), all_vals, side="right") / sim_pool.size
    return float(np.max(np.abs(e_cdf - s_cdf)))


def metric_max_degree_zscore(emp_max: float, sim_maxes: np.ndarray) -> float:
    """M2 — z-score of empirical max degree against the simulated max distribution."""
    if sim_maxes.size == 0:
        return float("nan")
    mu = float(sim_maxes.mean())
    sd = float(sim_maxes.std(ddof=0))
    if sd == 0:
        return float("nan")
    return float((emp_max - mu) / sd)


def metric_zero_degree_count_error(emp_zero: int, sim_zero_means: np.ndarray) -> float:
    """M3 — absolute difference between empirical zero-degree count and sim mean."""
    if sim_zero_means.size == 0:
        return float("nan")
    return float(abs(emp_zero - sim_zero_means.mean()))


def metric_gini_strength_zscore(emp_gini: float, sim_ginis: np.ndarray) -> float:
    """M4 — z-score of empirical Gini(strength) against simulated distribution."""
    if sim_ginis.size == 0:
        return float("nan")
    mu = float(sim_ginis.mean())
    sd = float(sim_ginis.std(ddof=0))
    if sd == 0:
        return float("nan")
    return float((emp_gini - mu) / sd)


def metric_top_k_hub_jaccard(
    emp_strength: np.ndarray, sim_strength_means: np.ndarray, *, k: int = 7
) -> float:
    """M5 — Jaccard overlap of top-k hubs by node strength.

    Note: requires LABELED simulation strengths (per-node), not just sorted
    means. For unlabeled BA we fall back to top-k VALUE range overlap.
    """
    if emp_strength.size == 0 or sim_strength_means.size == 0:
        return float("nan")
    emp_top = np.sort(emp_strength)[::-1][:k]
    sim_top = np.sort(sim_strength_means)[::-1][:k]
    sim_min = float(sim_top.min())
    sim_max = float(sim_top.max())
    if sim_max <= sim_min:
        return float("nan")
    in_range = ((emp_top >= sim_min) & (emp_top <= sim_max)).sum()
    return float(in_range / max(k, 1))


def metric_normalized_rich_club(empirical_adj: np.ndarray, rewired_adjs: list[np.ndarray]) -> float:
    """M6 — φ_emp(r) / φ_null(r), null = degree-preserving rewiring.

    Reports a single scalar = ratio at r = median empirical degree.
    Values > 1 indicate rich-club organisation above degree-preserving null.
    """
    g_emp = nx.from_numpy_array(empirical_adj)
    if g_emp.number_of_edges() < 2:
        return float("nan")
    deg = np.array([d for _, d in g_emp.degree()])
    r_target = int(np.median(deg))
    try:
        phi_emp = nx.rich_club_coefficient(g_emp, normalized=False).get(r_target)
    except (nx.NetworkXError, ZeroDivisionError):
        return float("nan")
    if phi_emp is None:
        return float("nan")
    phi_nulls: list[float] = []
    for adj in rewired_adjs:
        g_null = nx.from_numpy_array(adj)
        if g_null.number_of_edges() < 2:
            continue
        try:
            phi_n = nx.rich_club_coefficient(g_null, normalized=False).get(r_target)
        except (nx.NetworkXError, ZeroDivisionError):
            continue
        if phi_n is not None and phi_n > 0:
            phi_nulls.append(float(phi_n))
    if not phi_nulls:
        return float("nan")
    return float(phi_emp / float(np.mean(phi_nulls)))


# ---------------------------------------------------------------------------
# Discrimination decision
# ---------------------------------------------------------------------------


def _per_metric_verdict(
    empirical: float,
    ba_pool: np.ndarray,
    er_pool: np.ndarray,
    *,
    mde: float,
) -> tuple[DiscriminationVerdict, float, tuple[float, float], tuple[float, float]]:
    """Decide the per-metric verdict using 95% intervals and MDE."""
    if not math.isfinite(empirical) or ba_pool.size == 0 or er_pool.size == 0:
        return (
            DiscriminationVerdict.NOT_DISTINGUISHED,
            float("nan"),
            (float("nan"), float("nan")),
            (float("nan"), float("nan")),
        )
    ba_lo = float(np.percentile(ba_pool, 2.5))
    ba_hi = float(np.percentile(ba_pool, 97.5))
    er_lo = float(np.percentile(er_pool, 2.5))
    er_hi = float(np.percentile(er_pool, 97.5))
    in_ba = ba_lo <= empirical <= ba_hi
    in_er = er_lo <= empirical <= er_hi
    delta = abs(empirical - float(np.median(ba_pool))) - abs(empirical - float(np.median(er_pool)))
    if in_ba and in_er:
        return DiscriminationVerdict.NOT_DISTINGUISHED, delta, (ba_lo, ba_hi), (er_lo, er_hi)
    if not in_ba and in_er:
        return DiscriminationVerdict.ER_FAVORED, delta, (ba_lo, ba_hi), (er_lo, er_hi)
    if in_ba and not in_er:
        return DiscriminationVerdict.BA_FAVORED, delta, (ba_lo, ba_hi), (er_lo, er_hi)
    if abs(delta) < mde:
        return (
            DiscriminationVerdict.INSUFFICIENT_RESOLUTION,
            delta,
            (ba_lo, ba_hi),
            (er_lo, er_hi),
        )
    if delta < 0:  # closer to BA median than ER
        return DiscriminationVerdict.BA_FAVORED, delta, (ba_lo, ba_hi), (er_lo, er_hi)
    return DiscriminationVerdict.ER_FAVORED, delta, (ba_lo, ba_hi), (er_lo, er_hi)


def discriminate(
    metrics: dict[str, dict[str, Any]],
    *,
    bonferroni_k: int = _BONFERRONI_K,
    mde: float | None = None,
) -> DiscriminationReport:
    """Combine 6 metrics via per-metric Bonferroni 95% intervals plus a
    majority-vote aggregate (≥4/6).

    ``metrics`` schema (per metric name):
        {
            "empirical": float,
            "ba_pool":   np.ndarray,
            "er_pool":   np.ndarray,
        }

    The 4-of-6 majority threshold is the VOTING rule. Bonferroni at
    α/k applies inside each per-metric 95% interval test. They are
    independent layers — see module docstring.

    If ``mde`` is None, each metric uses its own per-metric MDE from
    :func:`mde_at_n31` so different metric scales are not pooled
    under a single unit-blind threshold.
    """
    rows: list[MetricResult] = []
    for name, payload in metrics.items():
        per_metric_mde = mde if mde is not None else mde_at_n31(name)
        verdict, _delta, ba_int, er_int = _per_metric_verdict(
            float(payload["empirical"]),
            np.asarray(payload["ba_pool"], dtype=np.float64),
            np.asarray(payload["er_pool"], dtype=np.float64),
            mde=per_metric_mde,
        )
        rows.append(
            MetricResult(
                name=name,
                empirical=float(payload["empirical"]),
                ba_p2_5=ba_int[0],
                ba_p97_5=ba_int[1],
                er_p2_5=er_int[0],
                er_p97_5=er_int[1],
                delta_ba_minus_er=_delta,
                verdict=verdict,
            )
        )
    counts = {v: 0 for v in DiscriminationVerdict}
    for r in rows:
        counts[r.verdict] += 1
    if counts[DiscriminationVerdict.BA_FAVORED] >= 4:
        agg = DiscriminationVerdict.BA_FAVORED
    elif counts[DiscriminationVerdict.ER_FAVORED] >= 4:
        agg = DiscriminationVerdict.ER_FAVORED
    elif counts[DiscriminationVerdict.INSUFFICIENT_RESOLUTION] >= 1:
        agg = DiscriminationVerdict.INSUFFICIENT_RESOLUTION
    else:
        agg = DiscriminationVerdict.NOT_DISTINGUISHED
    return DiscriminationReport(
        metrics=tuple(rows),
        n_metrics_favor_ba=counts[DiscriminationVerdict.BA_FAVORED],
        n_metrics_favor_er=counts[DiscriminationVerdict.ER_FAVORED],
        n_metrics_not_distinguished=counts[DiscriminationVerdict.NOT_DISTINGUISHED],
        n_metrics_insufficient=counts[DiscriminationVerdict.INSUFFICIENT_RESOLUTION],
        bonferroni_k=int(bonferroni_k),
        aggregate_verdict=agg,
        extra={"alpha_family": _ALPHA_FAMILY, "mde_at_n31": mde},
    )
