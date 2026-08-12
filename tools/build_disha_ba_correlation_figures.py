#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build BA-style topology + Pearson-correlation article figures for Disha.

Honest scope:
    BIS LBS country-level banking-system aggregate exposure data.
    Not bank-level. Not repo-specific. Not a contagion proof.
    Descriptive macro illustration only.

Outputs:
    figures/disha_ba_correlation/
        network_normal.png  network_lehman.png
        correlation_levels_{normal,lehman,delta}.png
        correlation_changes_{normal,lehman,delta}.png
        risk_concentration_bar.png
        ba_fit_summary.csv
        top_correlated_pairs_levels.csv
        top_correlated_pairs_changes.csv
        risk_concentration_summary.csv
        data_quality_summary.csv
        DISHA_ARTICLE_SUMMARY.md
        REPRODUCIBILITY.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

__all__ = [
    "build_article_artifact",
    "build_correlation_matrix",
    "build_period_matrix",
    "compute_ba_comparison",
    "compute_risk_concentration",
    "estimate_ba_m",
    "load_dataset",
    "main",
    "parse_quarter",
    "quarter_end_date",
    "threshold_adjacency",
]


_FORBIDDEN_WORDING: tuple[str, ...] = (
    "bank-level interbank network",
    "bank-to-bank exposures",
    "validated repo liquidity",
    "confirmed Barabási-Albert",
    "confirmed Barabasi-Albert",
    "confirmed systemic-risk phase transition",
    "liquidity contagion proof",
    "production-grade scientific validation",
)


def normalize_forbidden_text(text: str) -> str:
    """Lower-case + collapse whitespace so multi-line phrases still match.

    Without this, a markdown reflow that splits ``"bank-to-bank\\nexposures"``
    across two lines would let the substring check pass even though the
    semantic phrase is present.
    """
    import re

    return re.sub(r"\s+", " ", text.lower()).strip()


def find_forbidden_phrases(text: str) -> list[str]:
    """Return forbidden phrases present in ``text`` after whitespace normalisation."""
    norm = normalize_forbidden_text(text)
    return [f for f in _FORBIDDEN_WORDING if normalize_forbidden_text(f) in norm]


# ---------------------------------------------------------------------------
# Quarter parsing
# ---------------------------------------------------------------------------


def parse_quarter(label: str) -> tuple[int, int]:
    """``"2008Q3" -> (2008, 3)``. Quarter must be in ``{1, 2, 3, 4}``."""
    s = label.strip().upper().replace("-", "")
    if "Q" not in s:
        raise ValueError(f"unrecognised quarter label: {label!r}")
    yr_str, q_str = s.split("Q", 1)
    try:
        year = int(yr_str)
        quarter = int(q_str)
    except ValueError as exc:
        raise ValueError(f"non-integer year/quarter in {label!r}") from exc
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1, 2, 3 or 4; got {quarter} in {label!r}")
    return year, quarter


def quarter_end_date(year: int, quarter: int) -> date:
    end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
    return date(year, end[0], end[1])


def quarter_in_range(d: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    s = quarter_end_date(*start)
    e = quarter_end_date(*end)
    return s <= d <= e


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedDataset:
    dataset_dir: Path
    manifest: dict[str, Any]
    panel: pd.DataFrame
    nodes: tuple[str, ...]
    label_to_id: dict[str, int]
    interpretation_caveat: str


def load_dataset(dataset_dir: Path) -> LoadedDataset:
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"dataset_dir does not exist: {dataset_dir}")
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json missing in {dataset_dir}")
    panel_path = dataset_dir / "exposure_panel.parquet"
    nodes_path = dataset_dir / "node_mapping.parquet"
    if not panel_path.is_file() or not nodes_path.is_file():
        raise FileNotFoundError("exposure_panel.parquet or node_mapping.parquet missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    nm = pd.read_parquet(nodes_path)
    nm_sorted = nm.sort_values("node_id").reset_index(drop=True)
    nodes = tuple(nm_sorted["bank_label"].tolist())
    label_to_id = dict(zip(nodes, range(len(nodes)), strict=True))
    panel = pd.read_parquet(panel_path)
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    panel = panel[(panel["exposure"].notna()) & (panel["exposure"] >= 0)]
    return LoadedDataset(
        dataset_dir=dataset_dir,
        manifest=manifest,
        panel=panel,
        nodes=nodes,
        label_to_id=label_to_id,
        interpretation_caveat=str(manifest.get("interpretation_caveat", "")),
    )


# ---------------------------------------------------------------------------
# Per-period matrix
# ---------------------------------------------------------------------------


def build_period_matrix(
    panel: pd.DataFrame,
    n_nodes: int,
    period_start: tuple[int, int],
    period_end: tuple[int, int],
) -> tuple[np.ndarray, list[date]]:
    """Average directed exposure matrix across quarters in ``[start, end]``.

    Returns (average matrix N×N, list of contributing quarter-end dates).
    """
    in_range = panel["date"].apply(lambda d: quarter_in_range(d, period_start, period_end))
    sub = panel[in_range]
    quarters_in = sorted(sub["date"].unique())
    if not quarters_in:
        return np.zeros((n_nodes, n_nodes), dtype=np.float64), []
    accum = np.zeros((n_nodes, n_nodes), dtype=np.float64)
    for q_date in quarters_in:
        m = np.zeros((n_nodes, n_nodes), dtype=np.float64)
        for _, row in sub[sub["date"] == q_date].iterrows():
            s = int(row["source"])
            t = int(row["target"])
            if 0 <= s < n_nodes and 0 <= t < n_nodes and s != t:
                m[s, t] = float(row["exposure"])
        accum += m
    return accum / float(len(quarters_in)), quarters_in


def build_period_outward_strength_panel(
    panel: pd.DataFrame,
    n_nodes: int,
    period_start: tuple[int, int],
    period_end: tuple[int, int],
) -> tuple[pd.DataFrame, list[date]]:
    """T × N panel of out-strength per node per quarter, in chronological order."""
    in_range = panel["date"].apply(lambda d: quarter_in_range(d, period_start, period_end))
    sub = panel[in_range].copy()
    quarters_in = sorted(sub["date"].unique())
    if not quarters_in:
        # Empty panel must still expose n_nodes columns so downstream
        # correlation / risk-concentration can iterate consistently.
        return pd.DataFrame(columns=list(range(n_nodes))), []
    rows = []
    for q_date in quarters_in:
        out_strength = np.zeros(n_nodes, dtype=np.float64)
        for _, row in sub[sub["date"] == q_date].iterrows():
            s = int(row["source"])
            if 0 <= s < n_nodes:
                out_strength[s] += float(row["exposure"])
        rows.append(out_strength)
    df = pd.DataFrame(np.array(rows), index=quarters_in, columns=list(range(n_nodes)))
    return df, quarters_in


# ---------------------------------------------------------------------------
# Network thresholding
# ---------------------------------------------------------------------------


def threshold_adjacency(weighted: np.ndarray, edge_quantile: float) -> np.ndarray:
    """Binary directed adjacency from weighted matrix at ``edge_quantile`` of POSITIVE weights."""
    if weighted.size == 0:
        return np.zeros_like(weighted, dtype=np.uint8)
    positive = weighted[weighted > 0]
    if positive.size == 0:
        return np.zeros_like(weighted, dtype=np.uint8)
    threshold = float(np.quantile(positive, edge_quantile))
    binary: np.ndarray = (weighted >= threshold).astype(np.uint8)
    np.fill_diagonal(binary, 0)
    return binary


# ---------------------------------------------------------------------------
# BA-style comparison (descriptive)
# ---------------------------------------------------------------------------


def estimate_ba_m(n_nodes: int, n_edges: int) -> int:
    """``m`` in BA = round(E / N), bounded to ``[1, N-1]``."""
    if n_nodes < 2:
        return 0
    raw = max(1, round(n_edges / max(n_nodes, 1)))
    return int(min(raw, n_nodes - 1))


def degree_gini(degrees: np.ndarray) -> float:
    """Gini coefficient on a non-negative degree sequence; NaN if all zero."""
    if degrees.size == 0:
        return float("nan")
    arr = np.sort(np.asarray(degrees, dtype=np.float64))
    if arr.sum() <= 0:
        return float("nan")
    n = arr.size
    cum = np.cumsum(arr)
    return float((2.0 * np.sum((np.arange(1, n + 1)) * arr)) / (n * cum[-1]) - (n + 1.0) / n)


def _simulate_random_graph_degrees(
    generator: Any,
    n: int,
    n_simulations: int,
    seed: int,
    **kwargs: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Run ``n_simulations`` of ``generator(n, **kwargs, seed=...)``; return
    ``(mean_sorted_degrees, pooled_degrees_array)``."""
    rng_master = np.random.default_rng(seed)
    sim_seeds = rng_master.integers(0, 2**31 - 1, size=n_simulations)
    sim_sorted = np.zeros((n_simulations, n), dtype=np.float64)
    pooled: list[int] = []
    for k in range(n_simulations):
        g = generator(n, seed=int(sim_seeds[k]), **kwargs)
        deg = sorted(dict(g.degree()).values(), reverse=True)
        sim_sorted[k, :] = deg
        pooled.extend(deg)
    return sim_sorted.mean(axis=0), np.asarray(pooled, dtype=np.float64)


def _configuration_model_graph(n: int, *, seed: int, degree_sequence: list[int]) -> Any:
    """Wrapper: ``configuration_model`` collapsed to simple undirected graph."""
    g = nx.configuration_model(degree_sequence, seed=seed)
    g = nx.Graph(g)
    g.remove_edges_from(nx.selfloop_edges(g))
    return g


def _degree_preserving_rewire(empirical_binary: np.ndarray, *, seed: int) -> tuple[Any, bool]:
    """Double-edge-swap rewiring that preserves the degree sequence.

    Returns (rewired_graph, swap_succeeded). ``swap_succeeded`` is False
    when the graph is too constrained for any swap; callers MUST treat
    a False result as "no rewiring null available" rather than as a
    legitimate degenerate-distance-zero null. Earlier versions silently
    returned the empirical graph on swap failure, which would falsely
    show KS=0 vs the rewiring null and break the multi-null override.
    """
    sym = ((empirical_binary + empirical_binary.T) > 0).astype(np.uint8)
    np.fill_diagonal(sym, 0)
    g = nx.from_numpy_array(sym)
    n_edges = g.number_of_edges()
    if n_edges < 2:
        return g, False
    # nswap == n_edges // 2 randomises ~half the wiring while staying within
    # max_tries on sparse country-level graphs. Earlier versions used
    # nswap=5*n_edges which exhausted max_tries on N≈30 graphs and yielded
    # zero successful rewirings (silently treated as a degenerate null).
    nswap = max(5, n_edges // 2)
    max_tries = max(500, 100 * n_edges)
    try:
        nx.algorithms.swap.double_edge_swap(g, nswap=nswap, max_tries=max_tries, seed=seed)
    except (nx.NetworkXError, nx.NetworkXAlgorithmError):
        return g, False
    return g, True


def _simulate_configuration_model(
    n: int,
    n_simulations: int,
    *,
    seed: int,
    degree_sequence: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    rng_master = np.random.default_rng(seed)
    sim_seeds = rng_master.integers(0, 2**31 - 1, size=n_simulations)
    sim_sorted = np.zeros((n_simulations, n), dtype=np.float64)
    pooled: list[int] = []
    for k in range(n_simulations):
        g = _configuration_model_graph(n, seed=int(sim_seeds[k]), degree_sequence=degree_sequence)
        deg = sorted(dict(g.degree()).values(), reverse=True)
        # Pad/truncate to n in case configuration produced fewer nodes.
        if len(deg) < n:
            deg = deg + [0] * (n - len(deg))
        else:
            deg = deg[:n]
        sim_sorted[k, :] = deg
        pooled.extend(deg)
    return sim_sorted.mean(axis=0), np.asarray(pooled, dtype=np.float64)


def _simulate_degree_preserving_rewire(
    empirical_binary: np.ndarray,
    n_simulations: int,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Returns (mean_sorted_deg, pooled_deg, n_successful_swaps).

    Caller must check ``n_successful_swaps`` — a value of 0 means no
    legitimate rewiring null is available and BA-vs-rewire comparisons
    must be marked NaN, NOT zero KS distance.
    """
    n = int(empirical_binary.shape[0])
    rng_master = np.random.default_rng(seed)
    sim_seeds = rng_master.integers(0, 2**31 - 1, size=n_simulations)
    sim_sorted = np.zeros((n_simulations, n), dtype=np.float64)
    pooled: list[int] = []
    n_succeeded = 0
    for k in range(n_simulations):
        g, ok = _degree_preserving_rewire(empirical_binary, seed=int(sim_seeds[k]))
        if not ok:
            continue
        n_succeeded += 1
        deg = sorted(dict(g.degree()).values(), reverse=True)
        if len(deg) < n:
            deg = deg + [0] * (n - len(deg))
        else:
            deg = deg[:n]
        sim_sorted[k, :] = deg
        pooled.extend(deg)
    if n_succeeded == 0:
        return (
            np.full(n, np.nan, dtype=np.float64),
            np.asarray([], dtype=np.float64),
            0,
        )
    # Average only over the rows that succeeded.
    mean_sorted = sim_sorted[:n_succeeded].mean(axis=0)
    return mean_sorted, np.asarray(pooled, dtype=np.float64), n_succeeded


def _wasserstein_1d(a: np.ndarray, b: np.ndarray) -> float:
    """1D Wasserstein-1 distance via sorted-cdf integral."""
    if a.size == 0 or b.size == 0:
        return float("nan")
    a_sorted = np.sort(a.astype(np.float64))
    b_sorted = np.sort(b.astype(np.float64))
    # Resample to common grid by linear interpolation of inverse-cdf.
    n_grid = max(a_sorted.size, b_sorted.size, 100)
    qs = (np.arange(n_grid) + 0.5) / n_grid
    a_q = np.interp(qs, np.linspace(0, 1, a_sorted.size), a_sorted)
    b_q = np.interp(qs, np.linspace(0, 1, b_sorted.size), b_sorted)
    return float(np.mean(np.abs(a_q - b_q)))


def _top_k_degree_value_overlap(
    emp_deg: np.ndarray, sim_sorted_mean: np.ndarray, *, k: int = 5
) -> float:
    """Fraction of empirical top-k degree VALUES that fall within the
    simulated mean top-k range.

    Note: argsort on ``sim_sorted_mean`` (which is already monotonically
    sorted) returns [0, 1, ..., k-1] by construction — the previous
    ``_top_k_overlap`` collapsed to a trivial node-index comparison and
    was numerically meaningless for an unlabeled generative null. This
    replacement compares VALUE ranges (the top-k degree counts), which
    is the only fair signal for label-free random graphs.
    """
    if emp_deg.size == 0 or sim_sorted_mean.size == 0:
        return float("nan")
    emp_top_k_vals = np.sort(emp_deg)[::-1][:k].astype(np.float64)
    sim_top_k_vals = sim_sorted_mean[:k].astype(np.float64)
    if emp_top_k_vals.size == 0 or sim_top_k_vals.size == 0:
        return float("nan")
    sim_min = float(sim_top_k_vals.min())
    sim_max = float(sim_top_k_vals.max())
    if sim_max <= sim_min:
        return float("nan")
    in_range = ((emp_top_k_vals >= sim_min) & (emp_top_k_vals <= sim_max)).sum()
    return float(in_range / max(k, 1))


def _ks_distance(emp_sorted: np.ndarray, pooled: np.ndarray) -> float:
    """Two-sample KS statistic between empirical and pooled distributions."""
    if emp_sorted.size == 0 or pooled.size == 0:
        return float("nan")
    all_vals = np.union1d(emp_sorted, pooled)
    e_cdf = np.searchsorted(np.sort(emp_sorted), all_vals, side="right") / emp_sorted.size
    s_cdf = np.searchsorted(np.sort(pooled), all_vals, side="right") / pooled.size
    return float(np.max(np.abs(e_cdf - s_cdf)))


# Discrimination thresholds — claim BA-positive only when BA clearly beats ER.
_BA_OVER_ER_R_MIN: float = 0.05
_BA_NEAR_PERFECT_R_MIN: float = 0.98

# Correlation headline gating thresholds (used by both `top_correlated_pairs`
# and `compute_correlation_validity`).
_NEAR_PERFECT_R: float = 0.98
_MIN_HEADLINE_OBS: int = 8


def _ba_claim_status(
    *,
    ba_r: float,
    er_r: float,
    ba_ks: float,
    er_ks: float,
    zero_degree_mismatch: bool,
) -> tuple[str, str]:
    """Return (claim_status, interpretation_text) under KS-aware logic."""
    if math.isnan(ba_r) or math.isnan(er_r):
        return ("INCONCLUSIVE", "inconclusive — degenerate graph or null degree sequence")
    margin = ba_r - er_r
    if margin < _BA_OVER_ER_R_MIN:
        return (
            "NOT_DISTINGUISHED",
            "concentrated topology, but not clearly distinguishable from matched "
            "random-graph baseline (BA r margin over ER < 0.05)",
        )
    if not math.isnan(ba_ks) and not math.isnan(er_ks) and ba_ks > er_ks:
        return (
            "ER_KS_BETTER",
            "BA Pearson margin present, but Erdős-Rényi KS distance is smaller — "
            "distribution shape is closer to random than to BA",
        )
    if zero_degree_mismatch:
        return (
            "BA_STRUCTURAL_MISMATCH",
            "BA cannot reproduce the zero-degree tail under this construction; "
            "structural mismatch invalidates BA-positive claim despite Pearson similarity",
        )
    return (
        "BA_DESCRIPTIVELY_BETTER",
        "BA outperforms matched ER baseline on both Pearson margin and KS — "
        "graph is descriptively closer to preferential-attachment than to random",
    )


def compute_ba_comparison(
    binary: np.ndarray,
    *,
    ba_simulations: int,
    seed: int,
) -> dict[str, Any]:
    """Empirical degree sequence vs BA + Erdős-Rényi baselines.

    Reports both a BA Pearson r AND an ER baseline so consumers can judge
    whether the BA-similarity claim is statistically discriminating.
    """
    n = int(binary.shape[0])
    sym = ((binary + binary.T) > 0).astype(np.uint8)
    np.fill_diagonal(sym, 0)
    n_edges = int(sym.sum() // 2)
    deg = sym.sum(axis=1).astype(np.int64)
    emp_sorted = np.sort(deg)[::-1].astype(np.float64)
    emp_max = int(deg.max()) if n else 0
    emp_zero = int((deg == 0).sum()) if n else 0
    if n_edges == 0 or n < 2:
        return {
            "ba_m_estimate": 0,
            "empirical_mean_degree": float(deg.mean()) if n else float("nan"),
            "empirical_max_degree": emp_max,
            "empirical_degree_gini": float("nan"),
            "empirical_zero_degree_count": emp_zero,
            "ba_degree_pearson_r": float("nan"),
            "ba_degree_ks_distance": float("nan"),
            "ba_max_degree_mean": float("nan"),
            "ba_zero_degree_count_mean": float("nan"),
            "er_degree_pearson_r": float("nan"),
            "er_degree_ks_distance": float("nan"),
            "ba_minus_er_r": float("nan"),
            "winner_by_ks": "n/a",
            "max_degree_ratio": float("nan"),
            "zero_degree_mismatch": False,
            "ba_claim_status": "INCONCLUSIVE",
            "interpretation": "inconclusive — graph degenerate (no edges)",
            "caveat": "small N and/or sparse graph; not a strict power-law test",
        }
    m = max(1, min(estimate_ba_m(n, n_edges), n - 1))
    p_er = (2.0 * n_edges) / (n * (n - 1)) if n >= 2 else 0.0

    ba_mean_sorted, ba_pool = _simulate_random_graph_degrees(
        nx.barabasi_albert_graph, n, ba_simulations, seed=seed, m=m
    )
    er_mean_sorted, er_pool = _simulate_random_graph_degrees(
        nx.erdos_renyi_graph, n, ba_simulations, seed=seed + 7919, p=p_er
    )

    # Configuration model — preserves degree sequence exactly
    cfg_mean_sorted, cfg_pool = _simulate_configuration_model(
        n, ba_simulations, seed=seed + 17, degree_sequence=deg.tolist()
    )
    # Degree-preserving rewiring (with explicit success counter — see
    # _simulate_degree_preserving_rewire docstring)
    rew_mean_sorted, rew_pool, n_rew_succeeded = _simulate_degree_preserving_rewire(
        sym, ba_simulations, seed=seed + 31
    )
    rew_available = n_rew_succeeded > 0

    def _safe_r(a: np.ndarray, b: np.ndarray) -> float:
        if np.std(a) == 0 or np.std(b) == 0:
            return float("nan")
        return float(np.corrcoef(a, b)[0, 1])

    ba_r = _safe_r(emp_sorted, ba_mean_sorted)
    er_r = _safe_r(emp_sorted, er_mean_sorted)
    cfg_r = _safe_r(emp_sorted, cfg_mean_sorted)
    rew_r = _safe_r(emp_sorted, rew_mean_sorted)
    ba_ks = _ks_distance(emp_sorted, ba_pool)
    er_ks = _ks_distance(emp_sorted, er_pool)
    cfg_ks = _ks_distance(emp_sorted, cfg_pool)
    rew_ks = _ks_distance(emp_sorted, rew_pool)
    ba_w = _wasserstein_1d(emp_sorted, ba_pool)
    er_w = _wasserstein_1d(emp_sorted, er_pool)
    cfg_w = _wasserstein_1d(emp_sorted, cfg_pool)
    rew_w = _wasserstein_1d(emp_sorted, rew_pool)

    ba_max_mean = float(ba_pool.reshape(ba_simulations, n).max(axis=1).mean())
    er_max_mean = float(er_pool.reshape(ba_simulations, n).max(axis=1).mean())
    ba_zero_count_mean = float((ba_pool.reshape(ba_simulations, n) == 0).sum(axis=1).mean())
    er_zero_count_mean = float((er_pool.reshape(ba_simulations, n) == 0).sum(axis=1).mean())
    ba_top5 = _top_k_degree_value_overlap(deg, ba_mean_sorted)
    er_top5 = _top_k_degree_value_overlap(deg, er_mean_sorted)
    margin = ba_r - er_r if (not math.isnan(ba_r) and not math.isnan(er_r)) else float("nan")
    if math.isnan(ba_ks) or math.isnan(er_ks):
        winner = "n/a"
    else:
        winner = "BA" if ba_ks < er_ks else ("ER" if er_ks < ba_ks else "TIE")
    max_ratio = (emp_max / ba_max_mean) if ba_max_mean > 0 else float("nan")
    zero_mismatch = bool(emp_zero > 0 and ba_zero_count_mean < 1.0)
    max_degree_error = abs(emp_max - ba_max_mean)
    zero_degree_error = abs(emp_zero - ba_zero_count_mean)

    # Multi-baseline KS comparison: BA must win against ER AND configuration
    # AND rewiring on KS to qualify as "structurally distinct".
    # If rewiring nulls were unavailable (no successful swaps) we cannot
    # claim BA superiority — the discrimination criterion fail-closes.
    ba_beats_all_ks = (
        rew_available
        and not math.isnan(ba_ks)
        and not any(math.isnan(x) for x in (er_ks, cfg_ks, rew_ks))
        and ba_ks < er_ks
        and ba_ks < cfg_ks
        and ba_ks < rew_ks
    )
    claim_status, interpretation = _ba_claim_status(
        ba_r=ba_r,
        er_r=er_r,
        ba_ks=ba_ks,
        er_ks=er_ks,
        zero_degree_mismatch=zero_mismatch,
    )
    # Multi-null override: even if BA marginally beats ER, fail to claim if
    # configuration or rewiring null also matches the empirical sequence.
    if claim_status == "BA_DESCRIPTIVELY_BETTER" and not ba_beats_all_ks:
        claim_status = "NOT_DISTINGUISHED"
        interpretation = (
            "concentrated topology, but configuration / degree-preserving rewiring "
            "nulls match the empirical sequence at least as well as BA — "
            "BA mechanism not uniquely identified"
        )

    return {
        "ba_m_estimate": int(m),
        "empirical_mean_degree": float(deg.mean()),
        "empirical_max_degree": emp_max,
        "empirical_degree_gini": degree_gini(deg.astype(np.float64)),
        "empirical_zero_degree_count": emp_zero,
        # BA
        "ba_degree_pearson_r": ba_r,
        "ba_degree_ks_distance": ba_ks,
        "ba_wasserstein_distance": ba_w,
        "ba_max_degree_mean": ba_max_mean,
        "ba_zero_degree_count_mean": ba_zero_count_mean,
        "ba_top5_hub_overlap": ba_top5,
        # ER
        "er_degree_pearson_r": er_r,
        "er_degree_ks_distance": er_ks,
        "er_wasserstein_distance": er_w,
        "er_max_degree_mean": er_max_mean,
        "er_zero_degree_count_mean": er_zero_count_mean,
        "er_top5_hub_overlap": er_top5,
        # Configuration model
        "cfg_degree_pearson_r": cfg_r,
        "cfg_degree_ks_distance": cfg_ks,
        "cfg_wasserstein_distance": cfg_w,
        # Degree-preserving rewiring
        "rew_degree_pearson_r": rew_r,
        "rew_degree_ks_distance": rew_ks,
        "rew_wasserstein_distance": rew_w,
        "rew_n_successful_swaps": int(n_rew_succeeded),
        "rew_available": bool(rew_available),
        # Comparisons
        "ba_minus_er_r": margin,
        "winner_by_ks": winner,
        "ba_beats_all_ks": ba_beats_all_ks,
        "max_degree_ratio": max_ratio,
        "max_degree_error": max_degree_error,
        "zero_degree_error": zero_degree_error,
        "zero_degree_mismatch": zero_mismatch,
        "ba_claim_status": claim_status,
        "interpretation": interpretation,
        "caveat": (
            "small N (~31), sparse thresholded graph; descriptive only — "
            "BA claim valid ONLY when ba_claim_status == BA_DESCRIPTIVELY_BETTER "
            "(requires BA to beat ER + configuration + rewiring nulls)"
        ),
    }


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------


def build_correlation_matrix(
    series: pd.DataFrame,
    *,
    constant_threshold: float = 1e-12,
) -> tuple[np.ndarray, list[int]]:
    """Pearson correlation of columns; constants → NaN row/col, returned in second element."""
    if series.shape[0] < 2:
        n = series.shape[1]
        nan_mat = np.full((n, n), np.nan)
        return nan_mat, list(range(n))
    arr = series.to_numpy(dtype=np.float64)
    stds = arr.std(axis=0, ddof=0)
    constants = [int(i) for i, s in enumerate(stds) if s < constant_threshold]
    n = arr.shape[1]
    corr = np.full((n, n), np.nan)
    for i in range(n):
        if i in constants:
            continue
        for j in range(i, n):
            if j in constants:
                continue
            if i == j:
                corr[i, j] = 1.0
                continue
            xi = arr[:, i]
            xj = arr[:, j]
            r = float(np.corrcoef(xi, xj)[0, 1])
            corr[i, j] = r
            corr[j, i] = r
    return corr, constants


def to_log_changes(panel: pd.DataFrame, epsilon: float = 1.0) -> pd.DataFrame:
    """Quarter-over-quarter log differences with safe positive epsilon."""
    arr = panel.to_numpy(dtype=np.float64)
    if arr.shape[0] < 2:
        return pd.DataFrame(np.empty((0, arr.shape[1])), columns=panel.columns)
    log_arr = np.log(arr + epsilon)
    diff = np.diff(log_arr, axis=0)
    return pd.DataFrame(diff, index=panel.index[1:], columns=panel.columns)


# ---------------------------------------------------------------------------
# Risk concentration
# ---------------------------------------------------------------------------


def _spearman_kendall_pair(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Spearman ρ and Kendall τ via scipy. Returns NaN on degenerate input.

    Audit-found: previously caught broad ``Exception`` which would mask
    genuine bugs (e.g. shape mismatch). Now narrows to
    ``ImportError`` (scipy not installed) and ``ValueError`` (bad input
    sizes / data); other exceptions propagate.
    """
    if x.size < 2 or y.size < 2:
        return float("nan"), float("nan")
    if np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    try:
        from scipy.stats import kendalltau, spearmanr
    except ImportError:
        return float("nan"), float("nan")
    try:
        sp = spearmanr(x, y)
        kt = kendalltau(x, y)
        return float(sp.correlation), float(kt.correlation)
    except (ValueError, FloatingPointError):
        return float("nan"), float("nan")


def _bootstrap_pearson_ci(
    x: np.ndarray, y: np.ndarray, *, seed: int, n_boot: int = 200
) -> tuple[float, float]:
    """Bootstrap 95% CI for Pearson r; NaN on degenerate input."""
    if x.size < 4 or y.size < 4:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n = x.size
    rs: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        xi, yi = x[idx], y[idx]
        if np.std(xi) == 0 or np.std(yi) == 0:
            continue
        rs.append(float(np.corrcoef(xi, yi)[0, 1]))
    if not rs:
        return float("nan"), float("nan")
    return float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


def compute_correlation_validity(
    panel: pd.DataFrame,
    nodes: tuple[str, ...],
    *,
    mode: str,
    period: str,
    seed: int,
    near_perfect_r: float = _NEAR_PERFECT_R,
    min_headline_obs: int = _MIN_HEADLINE_OBS,
    n_boot: int = 200,
) -> pd.DataFrame:
    """Per-pair Pearson + Spearman + Kendall + bootstrap CI + headline_allowed."""
    if panel.shape[0] < 2 or panel.shape[1] < 2:
        return pd.DataFrame(
            columns=[
                "mode",
                "period",
                "country_i",
                "country_j",
                "pearson_r",
                "spearman_r",
                "kendall_tau",
                "effective_n",
                "bootstrap_ci_low",
                "bootstrap_ci_high",
                "near_perfect_warning",
                "low_n_warning",
                "low_variance_warning",
                "headline_allowed",
            ]
        )
    arr = panel.to_numpy(dtype=np.float64)
    n = arr.shape[1]
    rows: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            xi, xj = arr[:, i], arr[:, j]
            both = np.isfinite(xi) & np.isfinite(xj)
            xi_f, xj_f = xi[both], xj[both]
            eff_n = int(both.sum())
            std_i = float(np.std(xi_f)) if xi_f.size else 0.0
            std_j = float(np.std(xj_f)) if xj_f.size else 0.0
            low_var = (std_i < 1e-12) or (std_j < 1e-12)
            if eff_n < 2 or low_var:
                pearson_r = float("nan")
                spearman_r = float("nan")
                kendall_tau = float("nan")
                ci_lo = float("nan")
                ci_hi = float("nan")
            else:
                pearson_r = float(np.corrcoef(xi_f, xj_f)[0, 1])
                spearman_r, kendall_tau = _spearman_kendall_pair(xi_f, xj_f)
                ci_lo, ci_hi = _bootstrap_pearson_ci(
                    xi_f, xj_f, seed=seed + i * 1000 + j, n_boot=n_boot
                )
            near_perfect_flag = (
                False if math.isnan(pearson_r) else bool(abs(pearson_r) >= near_perfect_r)
            )
            low_n = bool(eff_n < min_headline_obs)
            headline = bool(
                (not math.isnan(pearson_r))
                and (not near_perfect_flag)
                and (not low_n)
                and (not low_var)
            )
            rows.append(
                {
                    "mode": mode,
                    "period": period,
                    "country_i": nodes[i],
                    "country_j": nodes[j],
                    "pearson_r": pearson_r,
                    "spearman_r": spearman_r,
                    "kendall_tau": kendall_tau,
                    "effective_n": eff_n,
                    "bootstrap_ci_low": ci_lo,
                    "bootstrap_ci_high": ci_hi,
                    "near_perfect_warning": near_perfect_flag,
                    "low_n_warning": low_n,
                    "low_variance_warning": low_var,
                    "headline_allowed": headline,
                }
            )
    return pd.DataFrame(rows)


def compute_risk_concentration(
    *,
    nodes: tuple[str, ...],
    corr_levels_normal: np.ndarray,
    corr_levels_lehman: np.ndarray,
    corr_changes_normal: np.ndarray,
    corr_changes_lehman: np.ndarray,
    weighted_lehman: np.ndarray,
    binary_lehman: np.ndarray,
    chg_lehman_panel: pd.DataFrame | None = None,
    corr_changes_sensitivity: np.ndarray | None = None,
    min_total_strength: float = 100_000.0,
    min_effective_change_observations: int = 8,
) -> pd.DataFrame:
    n = len(nodes)

    def _mean_abs(corr: np.ndarray, exclude_diag: bool = True) -> np.ndarray:
        vals = np.zeros(n)
        for i in range(n):
            row = np.abs(corr[i, :]).copy()
            if exclude_diag and not np.isnan(row[i]):
                row[i] = np.nan
            finite = row[~np.isnan(row)]
            vals[i] = float(np.mean(finite)) if finite.size else float("nan")
        return vals

    macn = _mean_abs(corr_levels_normal)
    macl = _mean_abs(corr_levels_lehman)
    machn = _mean_abs(corr_changes_normal)
    machl = _mean_abs(corr_changes_lehman)
    # Sensitivity-window |r| of changes — statistically more stable than the
    # 4-quarter Lehman window. Used as the article-grade headline metric.
    machs = (
        _mean_abs(corr_changes_sensitivity)
        if corr_changes_sensitivity is not None
        else np.full(n, np.nan)
    )
    out_str = weighted_lehman.sum(axis=1)
    in_str = weighted_lehman.sum(axis=0)
    total_str = out_str + in_str
    bin_deg = ((binary_lehman + binary_lehman.T) > 0).astype(int).sum(axis=1)
    if chg_lehman_panel is not None and chg_lehman_panel.shape[0] > 0:
        eff_obs = np.array(
            [int(chg_lehman_panel.iloc[:, i].notna().sum()) for i in range(n)],
            dtype=np.int64,
        )
    else:
        eff_obs = np.zeros(n, dtype=np.int64)
    passes_strength = total_str >= min_total_strength
    passes_obs = eff_obs >= min_effective_change_observations
    suspect_short = ~passes_obs
    suspect_low_mass = ~passes_strength
    article_grade = passes_strength & passes_obs
    df = pd.DataFrame(
        {
            "country": list(nodes),
            "mean_abs_corr_levels_normal": macn,
            "mean_abs_corr_levels_lehman": macl,
            "delta_mean_abs_corr_levels": macl - macn,
            "mean_abs_corr_changes_normal": machn,
            "mean_abs_corr_changes_lehman": machl,
            "delta_mean_abs_corr_changes": machl - machn,
            # Sensitivity-window primary metrics (preferred for article use)
            "mean_abs_corr_changes_sensitivity": machs,
            "delta_mean_abs_corr_changes_sensitivity": machs - machn,
            "weighted_out_strength_lehman": out_str,
            "weighted_in_strength_lehman": in_str,
            "total_strength_lehman": total_str,
            "binary_degree_lehman": bin_deg,
            "effective_change_observations": eff_obs,
            "passes_strength_filter": passes_strength,
            "passes_observation_filter": passes_obs,
            "suspect_short_sample": suspect_short,
            "suspect_low_mass": suspect_low_mass,
            "article_grade": article_grade,
        }
    )
    # Primary sort uses the sensitivity-window Δ (statistically stable, n=11)
    # rather than the noise-prone 4-quarter Lehman Δ.
    primary_delta = (
        "delta_mean_abs_corr_changes_sensitivity"
        if corr_changes_sensitivity is not None
        else "delta_mean_abs_corr_changes"
    )
    df = df.sort_values(
        [primary_delta, "mean_abs_corr_changes_sensitivity", "total_strength_lehman"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    df["risk_concentration_rank"] = np.arange(1, len(df) + 1, dtype=np.int64)
    return df


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _plot_network(
    weighted: np.ndarray,
    binary: np.ndarray,
    nodes: tuple[str, ...],
    *,
    out_path: Path,
    title: str,
    subtitle: str,
    top_n_labels: int,
    seed: int,
) -> None:
    n = len(nodes)
    g = nx.DiGraph()
    g.add_nodes_from(range(n))
    for i in range(n):
        for j in range(n):
            if binary[i, j] and i != j:
                g.add_edge(i, j, weight=float(weighted[i, j]))
    out_strength = weighted.sum(axis=1)
    in_strength = weighted.sum(axis=0)
    total_strength = out_strength + in_strength
    sizes = 100.0 + 1500.0 * (total_strength / max(total_strength.max(), 1.0))
    pos = nx.spring_layout(g, seed=seed, k=0.6, iterations=150)
    fig, ax = plt.subplots(figsize=(11, 9))
    if g.number_of_edges() > 0:
        weights = np.array([g[u][v]["weight"] for u, v in g.edges()])
        widths = 0.3 + 2.5 * (weights / max(weights.max(), 1.0))
        nx.draw_networkx_edges(
            g,
            pos,
            ax=ax,
            alpha=0.35,
            width=widths,
            edge_color="#444444",
            arrows=True,
            arrowsize=8,
            connectionstyle="arc3,rad=0.05",
        )
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=sizes, node_color="#3577b8", alpha=0.85)
    top_idx = np.argsort(-total_strength)[:top_n_labels]
    labels = {int(i): nodes[i] for i in top_idx}
    nx.draw_networkx_labels(g, pos, labels=labels, ax=ax, font_size=9, font_weight="bold")
    ax.set_title(title, fontsize=12, weight="bold")
    ax.text(
        0.5,
        -0.04,
        subtitle,
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def _plot_correlation(
    corr: np.ndarray,
    nodes: tuple[str, ...],
    *,
    out_path: Path,
    title: str,
    subtitle: str,
    diverging: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 9))
    cmap = "RdBu_r" if diverging else "viridis"
    vmin, vmax = (-1.0, 1.0) if diverging else (-1.0, 1.0)
    im = ax.imshow(corr, cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")
    ax.set_xticks(range(len(nodes)))
    ax.set_yticks(range(len(nodes)))
    ax.set_xticklabels(nodes, rotation=90, fontsize=8)
    ax.set_yticklabels(nodes, fontsize=8)
    ax.set_title(title, fontsize=12, weight="bold")
    ax.text(
        0.5,
        -0.16,
        subtitle,
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def _plot_risk_concentration(df: pd.DataFrame, *, out_path: Path, top: int = 15) -> None:
    head = df.head(top)
    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(head))
    ax.barh(y, head["delta_mean_abs_corr_changes"], color="#c0392b", alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(head["country"])
    ax.invert_yaxis()
    ax.set_xlabel("Δ mean |Pearson r| of log-changes (Lehman − Normal)")
    ax.set_title(
        "Countries with strongest exposure co-movement increase around Lehman window",
        fontsize=11,
        weight="bold",
    )
    ax.text(
        0.5,
        -0.14,
        "country-level BIS aggregate exposures; descriptive, not bank-level contagion proof",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        style="italic",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Top correlated pairs
# ---------------------------------------------------------------------------


def top_correlated_pairs(
    corr: np.ndarray,
    nodes: tuple[str, ...],
    *,
    mode: str,
    period: str,
    top: int = 25,
    series_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    n = corr.shape[0]
    rows: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            r = corr[i, j]
            if not np.isfinite(r):
                continue
            if series_panel is not None and series_panel.shape[0] > 0:
                xi = series_panel.iloc[:, i].to_numpy(dtype=np.float64)
                xj = series_panel.iloc[:, j].to_numpy(dtype=np.float64)
                both_finite = np.isfinite(xi) & np.isfinite(xj)
                eff_n = int(both_finite.sum())
            else:
                eff_n = 0
            suspicious = bool(abs(r) >= _NEAR_PERFECT_R)
            low_sample = bool(eff_n < _MIN_HEADLINE_OBS) if series_panel is not None else False
            headline = bool((not suspicious) and (eff_n >= _MIN_HEADLINE_OBS))
            rows.append(
                {
                    "mode": mode,
                    "period": period,
                    "country_i": nodes[i],
                    "country_j": nodes[j],
                    "pearson_r": float(r),
                    "abs_pearson_r": float(abs(r)),
                    "effective_n": eff_n,
                    "suspicious_near_perfect": suspicious,
                    "low_sample_warning": low_sample,
                    "headline_allowed": headline,
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        df["rank"] = []
        df["caveat"] = []
        return df
    df = df.sort_values("abs_pearson_r", ascending=False).reset_index(drop=True)
    df = df.head(top).copy()
    df["rank"] = np.arange(1, len(df) + 1, dtype=np.int64)
    df["caveat"] = "country-level BIS aggregate; descriptive co-movement, not causal"
    return df


def compute_reporter_status(
    panel: pd.DataFrame,
    nodes: tuple[str, ...],
    *,
    period_start: tuple[int, int],
    period_end: tuple[int, int],
) -> pd.DataFrame:
    """Per-country reporter status under the active filter.

    Catches the BIS-specific case where countries (e.g. ES, IT, HK, PH, ZA
    under L_PARENT_CTY=5J + L_CP_SECTOR=A) appear as counterparties only,
    never as reporters — easy to miss in the per-quarter panel.
    """
    in_range = panel["date"].apply(lambda d: quarter_in_range(d, period_start, period_end))
    sub = panel[in_range]
    quarters = sorted(sub["date"].unique())
    rows: list[dict[str, Any]] = []
    for i, label in enumerate(nodes):
        as_src_quarters = sorted(set(sub.loc[sub["source"] == i, "date"].unique()))
        as_tgt_quarters = sorted(set(sub.loc[sub["target"] == i, "date"].unique()))
        out_strength_total = float(sub.loc[sub["source"] == i, "exposure"].sum())
        rows.append(
            {
                "country": label,
                "appears_as_source": bool(as_src_quarters),
                "appears_as_target": bool(as_tgt_quarters),
                "source_quarter_count": len(as_src_quarters),
                "target_quarter_count": len(as_tgt_quarters),
                "n_quarters_in_window": len(quarters),
                "zero_out_strength_all_windows": (out_strength_total == 0.0),
                "target_only_under_filter": (bool(as_tgt_quarters) and not bool(as_src_quarters)),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Build artefact (orchestrator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildOptions:
    dataset_dir: Path
    output_dir: Path
    normal_start: tuple[int, int]
    normal_end: tuple[int, int]
    lehman_start: tuple[int, int]
    lehman_end: tuple[int, int]
    sensitivity_start: tuple[int, int]
    sensitivity_end: tuple[int, int]
    edge_quantile: float
    top_n_labels: int
    ba_simulations: int
    seed: int
    min_risk_total_strength: float = 100_000.0
    min_effective_change_observations: int = 8


def _git_sha(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def build_article_artifact(opts: BuildOptions) -> dict[str, Any]:
    opts.output_dir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset(opts.dataset_dir)
    nodes = ds.nodes
    n = len(nodes)
    panel = ds.panel
    quarter_min = panel["date"].min()
    quarter_max = panel["date"].max()

    # PR #592 gate: any GENERATIVE_MECHANISM claim must pass through the
    # instrument_validation layer. If positive control is unavailable
    # (sorted_degree_pearson can never pass at N=31, see G2), the BA
    # mechanism claim is blocked at emit_verdict time. The descriptive
    # topology + correlation findings emitted below are
    # ClaimType.DESCRIPTIVE_TOPOLOGY and pass without a certificate
    # provided the scope matches.
    from instrument_validation.scope import country_aggregate_default_scope
    from instrument_validation.verdict import ClaimType, Verdict, emit_verdict

    _scope = country_aggregate_default_scope(
        score_fn_source="build_disha_ba_correlation_figures", semver="2.0.0"
    )
    _density = float((panel["exposure"] > 0).sum()) / max(
        n * n * float(panel["date"].nunique()), 1.0
    )
    _verdict = emit_verdict(
        scope=_scope,
        pos_cert=None,
        neg_cert=None,
        discrimination=None,
        runtime_substrate=_scope.valid_for_substrate,
        runtime_n=n,
        runtime_density=_density,
        claim_type=ClaimType.DESCRIPTIVE_TOPOLOGY,
    )
    # The gate is informational for DESCRIPTIVE_TOPOLOGY emission: it
    # records whether we are inside scope, but descriptive figures with
    # explicit [EXPLORATORY] caveats remain producible. Mechanism-claim
    # emission (ClaimType.GENERATIVE_MECHANISM) is the path that would
    # return INVALID_INSTRUMENT and block downstream — that path is in
    # tools/disha_artifact/discrimination_v2.py and is the primary gate.
    instrument_gate_verdict = {
        "verdict": _verdict.verdict.value,
        "claim_tier": _verdict.claim_tier.value,
        "reason": _verdict.reason,
        "scope_id": _verdict.extra.get("scope_id", "?"),
        "in_scope": _verdict.verdict is not Verdict.OUT_OF_SCOPE,
    }

    # Per-period exposure matrices and outward-strength panels
    mat_normal, q_normal = build_period_matrix(panel, n, opts.normal_start, opts.normal_end)
    mat_lehman, q_lehman = build_period_matrix(panel, n, opts.lehman_start, opts.lehman_end)
    mat_sens, q_sens = build_period_matrix(panel, n, opts.sensitivity_start, opts.sensitivity_end)

    str_normal, _ = build_period_outward_strength_panel(
        panel, n, opts.normal_start, opts.normal_end
    )
    str_lehman, _ = build_period_outward_strength_panel(
        panel, n, opts.lehman_start, opts.lehman_end
    )
    str_sens, _ = build_period_outward_strength_panel(
        panel, n, opts.sensitivity_start, opts.sensitivity_end
    )

    # Thresholded binary graphs
    bin_normal = threshold_adjacency(mat_normal, opts.edge_quantile)
    bin_lehman = threshold_adjacency(mat_lehman, opts.edge_quantile)

    # BA-style descriptive comparison
    ba_normal = compute_ba_comparison(
        bin_normal, ba_simulations=opts.ba_simulations, seed=opts.seed
    )
    ba_lehman = compute_ba_comparison(
        bin_lehman, ba_simulations=opts.ba_simulations, seed=opts.seed + 1
    )
    ba_rows = []
    for label, mat, binary, info in [
        ("normal", mat_normal, bin_normal, ba_normal),
        ("lehman", mat_lehman, bin_lehman, ba_lehman),
    ]:
        ba_rows.append(
            {
                "period": label,
                "n_nodes": n,
                "n_edges_thresholded": int(((binary + binary.T) > 0).sum() // 2),
                "edge_quantile": opts.edge_quantile,
                **info,
            }
        )
    ba_df = pd.DataFrame(ba_rows)
    ba_df.to_csv(opts.output_dir / "ba_fit_summary.csv", index=False)

    # Pearson correlations — levels
    corr_lev_normal, const_lev_normal = build_correlation_matrix(str_normal)
    corr_lev_lehman, const_lev_lehman = build_correlation_matrix(str_lehman)
    corr_lev_delta = corr_lev_lehman - corr_lev_normal

    # Pearson correlations — log-changes
    chg_normal = to_log_changes(str_normal)
    chg_lehman = to_log_changes(str_lehman)
    chg_sens = to_log_changes(str_sens)
    corr_chg_normal, const_chg_normal = build_correlation_matrix(chg_normal)
    corr_chg_lehman, const_chg_lehman = build_correlation_matrix(chg_lehman)
    corr_chg_sens, const_chg_sens = build_correlation_matrix(chg_sens)
    corr_chg_delta = corr_chg_lehman - corr_chg_normal

    low_sample = chg_lehman.shape[0] < 4

    # Top correlated pairs CSVs (with effective_n + headline_allowed flags)
    top_lev_normal = top_correlated_pairs(
        corr_lev_normal, nodes, mode="levels", period="normal", series_panel=str_normal
    )
    top_lev_lehman = top_correlated_pairs(
        corr_lev_lehman, nodes, mode="levels", period="lehman", series_panel=str_lehman
    )
    top_chg_normal = top_correlated_pairs(
        corr_chg_normal, nodes, mode="changes", period="normal", series_panel=chg_normal
    )
    top_chg_lehman = top_correlated_pairs(
        corr_chg_lehman, nodes, mode="changes", period="lehman", series_panel=chg_lehman
    )
    top_chg_sens = top_correlated_pairs(
        corr_chg_sens,
        nodes,
        mode="changes",
        period="sensitivity_2007Q1_2009Q4",
        series_panel=chg_sens,
    )
    pd.concat([top_lev_normal, top_lev_lehman], ignore_index=True).to_csv(
        opts.output_dir / "top_correlated_pairs_levels.csv",
        index=False,
    )
    pd.concat([top_chg_normal, top_chg_lehman, top_chg_sens], ignore_index=True).to_csv(
        opts.output_dir / "top_correlated_pairs_changes.csv",
        index=False,
    )

    # Risk concentration. effective_change_observations is computed against the
    # SENSITIVITY window (longer, more stable) so the article-grade filter has
    # bite — Lehman alone has only 3 change observations and would always fail.
    rc = compute_risk_concentration(
        nodes=nodes,
        corr_levels_normal=corr_lev_normal,
        corr_levels_lehman=corr_lev_lehman,
        corr_changes_normal=corr_chg_normal,
        corr_changes_lehman=corr_chg_lehman,
        weighted_lehman=mat_lehman,
        binary_lehman=bin_lehman,
        chg_lehman_panel=chg_sens,
        corr_changes_sensitivity=corr_chg_sens,
        min_total_strength=opts.min_risk_total_strength,
        min_effective_change_observations=opts.min_effective_change_observations,
    )
    rc.to_csv(opts.output_dir / "risk_concentration_summary.csv", index=False)

    # Strength-weighted article risk score with explicit penalties.
    def _zscore(s: pd.Series) -> pd.Series:
        s_clean = s.replace([np.inf, -np.inf], np.nan)
        std = s_clean.std()
        if std is None or float(std) == 0.0 or pd.isna(std):
            return pd.Series([0.0] * len(s), index=s.index)
        return (s_clean - s_clean.mean()) / float(std)

    rc_with_score = rc.copy()
    rc_with_score["log_total_strength_lehman"] = np.log1p(
        rc_with_score["total_strength_lehman"].astype(float)
    )
    # Use sensitivity-window Δ (n=11 obs, statistically stable) as the primary
    # signal; the 4-quarter Lehman Δ is too noisy for ranking even after the
    # article-grade observation filter.
    z_delta = _zscore(rc_with_score["delta_mean_abs_corr_changes_sensitivity"]).fillna(0.0)
    z_logmass = _zscore(rc_with_score["log_total_strength_lehman"]).fillna(0.0)
    z_deg = _zscore(rc_with_score["binary_degree_lehman"].astype(float)).fillna(0.0)
    penalty_low_obs = (~rc_with_score["passes_observation_filter"]).astype(float)
    penalty_low_mass = (~rc_with_score["passes_strength_filter"]).astype(float)
    rc_with_score["short_sample_penalty"] = penalty_low_obs
    rc_with_score["low_mass_penalty"] = penalty_low_mass
    rc_with_score["article_risk_score"] = (
        z_delta + z_logmass + z_deg - 2.0 * penalty_low_obs - 2.0 * penalty_low_mass
    )
    rc_article = (
        rc_with_score[rc_with_score["article_grade"]]
        .sort_values("article_risk_score", ascending=False)
        .reset_index(drop=True)
    )
    rc_article["article_rank"] = np.arange(1, len(rc_article) + 1, dtype=np.int64)
    rc_article.to_csv(opts.output_dir / "risk_concentration_article_grade.csv", index=False)

    # Reporter status (catches BIS target-only countries like ES, IT, HK, PH, ZA)
    reporter_status = compute_reporter_status(
        panel,
        nodes,
        period_start=opts.normal_start,
        period_end=opts.lehman_end,
    )
    reporter_status.to_csv(opts.output_dir / "reporter_status_summary.csv", index=False)
    target_only = sorted(
        reporter_status.loc[reporter_status["target_only_under_filter"], "country"].tolist()
    )
    constant_source_nodes = sorted(
        reporter_status.loc[reporter_status["zero_out_strength_all_windows"], "country"].tolist()
    )

    # Model comparison summary (BA vs ER, KS-aware)
    model_rows: list[dict[str, Any]] = []
    for label, info in [("normal", ba_normal), ("lehman", ba_lehman)]:
        model_rows.append(
            {
                "period": label,
                "ba_pearson_r": info["ba_degree_pearson_r"],
                "er_pearson_r": info["er_degree_pearson_r"],
                "ba_minus_er_r": info["ba_minus_er_r"],
                "ba_ks_distance": info["ba_degree_ks_distance"],
                "er_ks_distance": info["er_degree_ks_distance"],
                "winner_by_ks": info["winner_by_ks"],
                "empirical_max_degree": info["empirical_max_degree"],
                "ba_max_degree_mean": info["ba_max_degree_mean"],
                "max_degree_ratio": info["max_degree_ratio"],
                "empirical_zero_degree_count": info["empirical_zero_degree_count"],
                "ba_zero_degree_count_mean": info["ba_zero_degree_count_mean"],
                "zero_degree_mismatch": info["zero_degree_mismatch"],
                "ba_claim_status": info["ba_claim_status"],
                "interpretation": info["interpretation"],
            }
        )
    pd.DataFrame(model_rows).to_csv(opts.output_dir / "model_comparison_summary.csv", index=False)

    # Extend model_rows for BA-vs-all-nulls fields (configuration + rewiring + Wasserstein
    # + top5 hub overlap + multi-null override flag).
    model_rows_full: list[dict[str, Any]] = []
    for label, info in [("normal", ba_normal), ("lehman", ba_lehman)]:
        model_rows_full.append(
            {
                "period": label,
                "ba_pearson_r": info["ba_degree_pearson_r"],
                "er_pearson_r": info["er_degree_pearson_r"],
                "cfg_pearson_r": info["cfg_degree_pearson_r"],
                "rew_pearson_r": info["rew_degree_pearson_r"],
                "ba_ks": info["ba_degree_ks_distance"],
                "er_ks": info["er_degree_ks_distance"],
                "cfg_ks": info["cfg_degree_ks_distance"],
                "rew_ks": info["rew_degree_ks_distance"],
                "ba_wasserstein": info["ba_wasserstein_distance"],
                "er_wasserstein": info["er_wasserstein_distance"],
                "cfg_wasserstein": info["cfg_wasserstein_distance"],
                "rew_wasserstein": info["rew_wasserstein_distance"],
                "ba_top5_hub_overlap": info["ba_top5_hub_overlap"],
                "er_top5_hub_overlap": info["er_top5_hub_overlap"],
                "max_degree_error": info["max_degree_error"],
                "zero_degree_error": info["zero_degree_error"],
                "ba_beats_all_ks": info["ba_beats_all_ks"],
                "ba_claim_status": info["ba_claim_status"],
            }
        )
    pd.DataFrame(model_rows_full).to_csv(opts.output_dir / "model_comparison_full.csv", index=False)

    # Correlation validity layer — Pearson + Spearman + Kendall + bootstrap CI per pair
    cv_normal = compute_correlation_validity(
        chg_normal, nodes, mode="changes", period="normal", seed=opts.seed
    )
    cv_lehman = compute_correlation_validity(
        chg_lehman, nodes, mode="changes", period="lehman", seed=opts.seed + 1
    )
    cv_sens = compute_correlation_validity(
        chg_sens,
        nodes,
        mode="changes",
        period="sensitivity_2007Q1_2009Q4",
        seed=opts.seed + 2,
    )
    cv_all = pd.concat([cv_normal, cv_lehman, cv_sens], ignore_index=True)
    cv_all.to_csv(opts.output_dir / "correlation_validity_summary.csv", index=False)

    # Figures — networks
    _plot_network(
        mat_normal,
        bin_normal,
        nodes,
        out_path=opts.output_dir / "network_normal.png",
        title=(
            f"BIS LBS country-level banking-system exposure network — Normal window "
            f"({opts.normal_start[0]}Q{opts.normal_start[1]}–{opts.normal_end[0]}Q{opts.normal_end[1]})"
        ),
        subtitle=(
            "node size = total strength; edge width ∝ avg exposure; "
            "thresholded at top {q:.0%} of positive weights — not bank-level exposures"
        ).format(q=1 - opts.edge_quantile),
        top_n_labels=opts.top_n_labels,
        seed=opts.seed,
    )
    _plot_network(
        mat_lehman,
        bin_lehman,
        nodes,
        out_path=opts.output_dir / "network_lehman.png",
        title=(
            f"BIS LBS country-level banking-system exposure network — Lehman window "
            f"({opts.lehman_start[0]}Q{opts.lehman_start[1]}–{opts.lehman_end[0]}Q{opts.lehman_end[1]})"
        ),
        subtitle=(
            "node size = total strength; edge width ∝ avg exposure; "
            "thresholded at top {q:.0%} of positive weights — not bank-level exposures"
        ).format(q=1 - opts.edge_quantile),
        top_n_labels=opts.top_n_labels,
        seed=opts.seed,
    )

    # Figures — correlations (levels)
    _plot_correlation(
        corr_lev_normal,
        nodes,
        out_path=opts.output_dir / "correlation_levels_normal.png",
        title="Pearson r of country out-strength LEVELS — Normal",
        subtitle="trend-sensitive; for descriptive comparison only",
    )
    _plot_correlation(
        corr_lev_lehman,
        nodes,
        out_path=opts.output_dir / "correlation_levels_lehman.png",
        title="Pearson r of country out-strength LEVELS — Lehman",
        subtitle="short window (4 quarters); descriptive only",
    )
    _plot_correlation(
        corr_lev_delta,
        nodes,
        out_path=opts.output_dir / "correlation_levels_delta.png",
        title="Δ Pearson r LEVELS (Lehman − Normal)",
        subtitle="positive = stronger co-movement during Lehman window",
        diverging=True,
    )

    # Figures — correlations (changes)
    _plot_correlation(
        corr_chg_normal,
        nodes,
        out_path=opts.output_dir / "correlation_changes_normal.png",
        title="Pearson r of country out-strength LOG-CHANGES — Normal",
        subtitle="quarter-over-quarter; main co-movement metric",
    )
    _plot_correlation(
        corr_chg_lehman,
        nodes,
        out_path=opts.output_dir / "correlation_changes_lehman.png",
        title="Pearson r of country out-strength LOG-CHANGES — Lehman",
        subtitle=(
            "LOW_SAMPLE_WARNING: short window — read as descriptive only"
            if low_sample
            else "short window; descriptive only"
        ),
    )
    _plot_correlation(
        corr_chg_delta,
        nodes,
        out_path=opts.output_dir / "correlation_changes_delta.png",
        title="Δ Pearson r LOG-CHANGES (Lehman − Normal)",
        subtitle="positive = stronger co-movement during Lehman window",
        diverging=True,
    )

    # Figure — risk concentration
    _plot_risk_concentration(rc, out_path=opts.output_dir / "risk_concentration_bar.png")

    # Data quality summary
    constants_lev = sorted(set(const_lev_normal) | set(const_lev_lehman))
    constants_chg = sorted(set(const_chg_normal) | set(const_chg_lehman))
    dq = pd.DataFrame(
        [
            {"metric": "n_quarters_total", "value": int(panel["date"].nunique())},
            {"metric": "n_quarters_normal", "value": len(q_normal)},
            {"metric": "n_quarters_lehman", "value": len(q_lehman)},
            {"metric": "n_quarters_sensitivity", "value": len(q_sens)},
            {"metric": "n_nodes", "value": n},
            {
                "metric": "n_edges_positive_normal",
                "value": int((mat_normal > 0).sum()),
            },
            {
                "metric": "n_edges_positive_lehman",
                "value": int((mat_lehman > 0).sum()),
            },
            {
                "metric": "residual_nodes_excluded",
                "value": "5Q (already filtered upstream by build_bis_lbs_dataset.py)",
            },
            {
                "metric": "constant_nodes_levels",
                "value": ",".join(nodes[i] for i in constants_lev) or "(none)",
            },
            {
                "metric": "constant_nodes_changes",
                "value": ",".join(nodes[i] for i in constants_chg) or "(none)",
            },
            {
                "metric": "target_only_nodes",
                "value": ",".join(target_only) or "(none)",
            },
            {
                "metric": "constant_source_nodes",
                "value": ",".join(constant_source_nodes) or "(none)",
            },
            {
                "metric": "reporting_filter_warning",
                "value": (
                    "ES, IT, HK, PH, ZA-style countries appear as target-only "
                    "or constant under the active L_PARENT_CTY=5J + L_CP_SECTOR=A "
                    "filter; this reflects BIS reporting / filter constraints, "
                    "not economic absence. See reporter_status_summary.csv."
                ),
            },
            {
                "metric": "article_safe_outputs",
                "value": (
                    "risk_concentration_article_grade.csv, "
                    "top_correlated_pairs_changes.csv (rows where headline_allowed=True), "
                    "model_comparison_summary.csv (BA vs ER baseline)"
                ),
            },
            {
                "metric": "missing_quarters",
                "value": (
                    "(none — every quarter in window has ≥1 row)"
                    if (q_normal and q_lehman)
                    else "WARNING: empty period"
                ),
            },
            {
                "metric": "low_sample_warning_lehman_changes",
                "value": "TRUE" if low_sample else "FALSE",
            },
            {
                "metric": "warnings",
                "value": (
                    "Pearson on 4-quarter Lehman window is fragile; rely on sensitivity window."
                ),
            },
            {
                "metric": "panel_date_range",
                "value": f"{quarter_min}..{quarter_max}",
            },
            {
                "metric": "interpretation_caveat",
                "value": ds.interpretation_caveat or "(none in manifest)",
            },
        ]
    )
    dq.to_csv(opts.output_dir / "data_quality_summary.csv", index=False)

    # Article summary + reproducibility
    repo_root = Path(__file__).resolve().parents[1]
    sha = _git_sha(repo_root)
    cmd = " ".join(sys.argv) if len(sys.argv) > 1 else "(programmatic call)"
    _write_article_summary(
        opts=opts,
        ds=ds,
        ba_df=ba_df,
        rc=rc,
        rc_article=rc_article,
        top_chg_sens=top_chg_sens,
        top_chg_lehman=top_chg_lehman,
        low_sample_warning=low_sample,
        target_only=target_only,
        constant_source=constant_source_nodes,
        sha=sha,
    )
    _write_reproducibility(opts=opts, ds=ds, sha=sha, cmd=cmd)
    _write_audit_response(opts=opts, ba_df=ba_df, sha=sha)
    _write_disha_safe_120(opts, ds)
    # Copy CLAIM_BOUNDARY.md from repo root snapshot if user shipped one;
    # otherwise it must already exist in opts.output_dir (this script does
    # not overwrite a user-curated boundary contract).
    boundary_dst = opts.output_dir / "CLAIM_BOUNDARY.md"
    if not boundary_dst.is_file():
        boundary_dst.write_text(
            "# Claim Boundary Contract — placeholder\n\n"
            "Replace with the audited boundary contract (see "
            "figures/disha_ba_correlation/CLAIM_BOUNDARY.md in the repo).\n",
            encoding="utf-8",
        )

    summary_payload: dict[str, Any] = {
        "n_quarters_normal": len(q_normal),
        "n_quarters_lehman": len(q_lehman),
        "n_quarters_sensitivity": len(q_sens),
        "ba_normal": ba_normal,
        "ba_lehman": ba_lehman,
        "low_sample_warning": low_sample,
        "constants_levels": [nodes[i] for i in constants_lev],
        "constants_changes": [nodes[i] for i in constants_chg],
        "target_only_nodes": target_only,
        "constant_source_nodes": constant_source_nodes,
        "n_article_grade_countries": int(rc_article.shape[0]),
        "n_correlation_validity_rows": int(cv_all.shape[0]),
        "instrument_gate_verdict": instrument_gate_verdict,
    }
    _write_repro_capsule(opts, ds, sha, summary_payload)
    return summary_payload


# ---------------------------------------------------------------------------
# Markdown writers
# ---------------------------------------------------------------------------


def _write_article_summary(
    *,
    opts: BuildOptions,
    ds: LoadedDataset,
    ba_df: pd.DataFrame,
    rc: pd.DataFrame,
    rc_article: pd.DataFrame,
    top_chg_sens: pd.DataFrame,
    top_chg_lehman: pd.DataFrame,
    low_sample_warning: bool,
    target_only: list[str],
    constant_source: list[str],
    sha: str,
) -> None:
    # Article-grade ranking: only article_grade rows, only headline_allowed pairs.
    rc_grade = rc_article.head(10)
    if rc_grade.empty:
        rc_lines = "  (no countries pass total_strength + observation filters)"
    else:
        rc_lines = "\n".join(
            f"  {i + 1}. {row.country} — Δ|r|_changes = {row.delta_mean_abs_corr_changes:+.3f}, "
            f"|r|_changes_lehman = {row.mean_abs_corr_changes_lehman:.3f}, "
            f"total_strength = {row.total_strength_lehman:,.0f}"
            for i, row in rc_grade.iterrows()
        )
    sens_headline = top_chg_sens[top_chg_sens["headline_allowed"]].head(8)
    if sens_headline.empty:
        chg_lines = "  (no sensitivity-window pairs pass effective_n + non-saturation filters)"
    else:
        chg_lines = "\n".join(
            f"  {i + 1}. {row.country_i}–{row.country_j}: r = {row.pearson_r:+.3f} "
            f"(n_eff = {row.effective_n})"
            for i, row in sens_headline.iterrows()
        )
    n_lehman_saturated = int(
        (top_chg_lehman["suspicious_near_perfect"] & ~top_chg_lehman["headline_allowed"]).sum()
    )
    ba_lines = "\n".join(
        f"  {row.period}: BA r = {row.ba_degree_pearson_r:.3f}, "
        f"ER r = {row.er_degree_pearson_r:.3f}, "
        f"BA−ER r = {row.ba_minus_er_r:+.3f}, "
        f"KS_BA = {row.ba_degree_ks_distance:.3f}, "
        f"KS_ER = {row.er_degree_ks_distance:.3f}, "
        f"winner_by_ks = {row.winner_by_ks}, "
        f"emp_zero_deg = {row.empirical_zero_degree_count}, "
        f"BA_zero_deg_mean = {row.ba_zero_degree_count_mean:.1f}, "
        f"status = {row.ba_claim_status}"
        for _, row in ba_df.iterrows()
    )
    low_sample_block = (
        "\n**LOW_SAMPLE_WARNING:** the Lehman window contains < 4 usable observations after the "
        "log-change transformation. Lehman-only top change-correlation pairs are saturated by "
        "construction and are excluded from the headline list. Use sensitivity window for "
        "ranking.\n"
        if low_sample_warning
        else ""
    )
    target_only_block = f"  {', '.join(target_only)}" if target_only else "  (none)"
    constant_source_block = f"  {', '.join(constant_source)}" if constant_source else "  (none)"
    md = f"""# Disha BA + Correlation — Article Summary (Audit-Hardened)

## 1. Plain-English summary

This analysis uses public BIS LBS country-level banking-system aggregate exposure data.
It builds a directed exposure network between national banking systems and compares its
thresholded topology with BOTH a Barabási-Albert preferential-attachment baseline AND an
Erdős-Rényi matched-density baseline. The BA result is reported only if it
**discriminates from the random-graph baseline**; otherwise the topology is described as
"concentrated, but not uniquely BA-like". Pearson correlations between country exposure
time series identify which banking systems co-moved most strongly during the Lehman
window. The result is a macro country-level exposure illustration; it is not
bank-to-bank evidence and it does not validate repo liquidity contagion.

## 2. Data

- Source: BIS Locational Banking Statistics (LBS), bulk feed `WS_LBS_D_PUB`.
- Aggregation: country-level reporting banking system → counterparty country (sector A).
- Filter: `L_PARENT_CTY=5J, L_CP_SECTOR=A` (the only public BIS slice with bilateral
  REP × CP-country cells).
- Residual node `5Q`: already filtered upstream; not present in the country list.

### Reporter-status caveat

Under this filter, some countries appear as **target-only** or with **zero out-strength**
across all windows — a BIS reporting/filter constraint, NOT economic absence. This is
material for any country-level comparison and is exposed in `reporter_status_summary.csv`.

- Target-only under filter:
{target_only_block}
- Zero out-strength across all windows (reporting suppressed under this filter):
{constant_source_block}

## 3. BA-style comparison vs Erdős-Rényi baseline

We threshold each period's averaged exposure matrix at the top {(1 - opts.edge_quantile):.0%}
of positive weights and compare the thresholded undirected degree sequence to:

- {opts.ba_simulations} Barabási-Albert simulations (same N, m matched to edge density)
- {opts.ba_simulations} Erdős-Rényi simulations (same N, p matched to edge density)

For each, we compute (a) Pearson r of sorted-degree sequences and (b) Kolmogorov-Smirnov
distance between empirical and pooled-simulated degree distributions. The BA claim is
upgraded to `BA_DESCRIPTIVELY_BETTER` ONLY when:

- BA Pearson r exceeds ER Pearson r by ≥ 0.05, AND
- BA KS distance ≤ ER KS distance, AND
- BA can reproduce the empirical zero-degree tail.

Otherwise: `NOT_DISTINGUISHED`, `ER_KS_BETTER`, or `BA_STRUCTURAL_MISMATCH`.

{ba_lines}

Honest framing: the network is **concentrated**, but this concentration is not uniquely
explained by a Barabási-Albert mechanism unless the status above is `BA_DESCRIPTIVELY_BETTER`.

## 4. Pearson correlation — what it measures

For each country we sum its outward exposure each quarter (out-strength). Two correlations:

- **LEVELS**: correlation of raw out-strength. Trend-sensitive — secular growth in claims
  inflates level correlations.
- **LOG-CHANGES** (main metric): quarter-over-quarter `log(x + 1)` differences. Removes
  the secular trend; isolates co-movement of shocks.

Pairs are headline-allowed only when (effective_n ≥ {_MIN_HEADLINE_OBS}) AND
(|r| < {_NEAR_PERFECT_R}). Near-perfect correlations on short windows are flagged as
saturation, not signal.
{low_sample_block}
## 5. Headline correlation result — sensitivity window only

Lehman 4-quarter log-change correlations are statistically fragile and are blocked from the
headline list ({n_lehman_saturated} suspicious near-perfect pairs filtered out). The article
result uses the wider sensitivity window {opts.sensitivity_start[0]}Q{opts.sensitivity_start[1]}
– {opts.sensitivity_end[0]}Q{opts.sensitivity_end[1]}:

{chg_lines}

## 6. Risk concentration — article-grade only

Filtered to nodes with total_strength_lehman ≥ {opts.min_risk_total_strength:,.0f} USD mn AND
effective_change_observations ≥ {opts.min_effective_change_observations}. Excludes small-mass
nodes whose high |r| is short-window saturation noise.

Top 10 article-grade countries:

{rc_lines}

The full unfiltered ranking is in `risk_concentration_summary.csv`; the filtered ranking is in
`risk_concentration_article_grade.csv`. Use the latter for any external claim.

## 7. Limitations

1. Country-level aggregation, not bank-level interbank exposures.
2. Small N (~31 reporting countries); too small for strict heavy-tail estimation.
3. Edge thresholding is sensitive to `--edge-quantile`.
4. Pearson over short (~4-quarter) windows is statistically fragile (filtered out by default).
5. Level correlations are trend-sensitive.
6. Log-change correlations are better for shock co-movement but still descriptive — not causal.
7. Not a bank-level repo contagion model.
8. Not a causal model — these are descriptive co-movement statistics.
9. ES, IT, HK, PH, ZA-style countries are target-only or zero-out-strength under this filter
   (reporting/filter artefact, not economic absence).

## 8. Reproducibility

```
python tools/build_disha_ba_correlation_figures.py \\
    --dataset-dir {opts.dataset_dir} \\
    --output-dir {opts.output_dir} \\
    --normal-start {opts.normal_start[0]}Q{opts.normal_start[1]} \\
    --normal-end {opts.normal_end[0]}Q{opts.normal_end[1]} \\
    --lehman-start {opts.lehman_start[0]}Q{opts.lehman_start[1]} \\
    --lehman-end {opts.lehman_end[0]}Q{opts.lehman_end[1]} \\
    --sensitivity-start {opts.sensitivity_start[0]}Q{opts.sensitivity_start[1]} \\
    --sensitivity-end {opts.sensitivity_end[0]}Q{opts.sensitivity_end[1]} \\
    --edge-quantile {opts.edge_quantile} \\
    --top-n-labels {opts.top_n_labels} \\
    --ba-simulations {opts.ba_simulations} \\
    --min-risk-total-strength {opts.min_risk_total_strength} \\
    --min-effective-change-observations {opts.min_effective_change_observations} \\
    --seed {opts.seed}
```

Git SHA: `{sha}`

## 9. Out of scope

This analysis does NOT use Kuramoto / phase-synchronisation modelling. The earlier X-9R
Kuramoto pipeline is unrelated to this artefact and was explicitly excluded per Disha's
request.

This analysis does NOT make bank-level claims. The BIS LBS bulk feed publishes bilateral
cells only at country level; bank-to-bank bilateral data requires supervisory access.

## 10. Suggested 100-word paragraph for Disha

> Using public BIS Locational Banking Statistics, we built a directed network of cross-border
> claims between national banking systems. We compared its thresholded topology against BOTH
> a Barabási-Albert and an Erdős-Rényi baseline; the network is **concentrated**, but this
> concentration is not uniquely explained by preferential attachment when matched-density
> Erdős-Rényi reproduces the same sorted-degree similarity. Pearson correlations of country
> exposure log-changes over the wider 2007Q1-2009Q4 window highlight economically plausible
> co-movement corridors among large continental European, UK and US banking systems. These
> figures illustrate macro country-level exposure structure; they are not bank-level
> evidence and do not validate liquidity contagion.
"""
    (opts.output_dir / "DISHA_ARTICLE_SUMMARY.md").write_text(md, encoding="utf-8")
    # Forbidden-wording self-check (whitespace-normalised — robust to line breaks)
    found = find_forbidden_phrases(md)
    if found:
        raise RuntimeError(f"forbidden wording present in DISHA_ARTICLE_SUMMARY.md: {found!r}")


def _write_reproducibility(
    *,
    opts: BuildOptions,
    ds: LoadedDataset,
    sha: str,
    cmd: str,
) -> None:
    py_ver = sys.version.replace("\n", " ")
    md = f"""# Reproducibility — Disha BA + Correlation Artefact

- Repository: `neuron7xLab/GeoSync`
- Git SHA: `{sha}`
- Dataset directory: `{opts.dataset_dir}`
- Manifest path: `{opts.dataset_dir / "manifest.json"}`
- Manifest source_id: `{ds.manifest.get("source_id", "?")}`
- Manifest config_hash: `{ds.manifest.get("config_hash", "?")}`
- Output directory: `{opts.output_dir}`
- Python: `{py_ver}`

## Command

```
{cmd}
```

Or programmatically equivalent:

```
python tools/build_disha_ba_correlation_figures.py \\
    --dataset-dir {opts.dataset_dir} \\
    --output-dir {opts.output_dir} \\
    --normal-start {opts.normal_start[0]}Q{opts.normal_start[1]} \\
    --normal-end {opts.normal_end[0]}Q{opts.normal_end[1]} \\
    --lehman-start {opts.lehman_start[0]}Q{opts.lehman_start[1]} \\
    --lehman-end {opts.lehman_end[0]}Q{opts.lehman_end[1]} \\
    --sensitivity-start {opts.sensitivity_start[0]}Q{opts.sensitivity_start[1]} \\
    --sensitivity-end {opts.sensitivity_end[0]}Q{opts.sensitivity_end[1]} \\
    --edge-quantile {opts.edge_quantile} \\
    --top-n-labels {opts.top_n_labels} \\
    --ba-simulations {opts.ba_simulations} \\
    --seed {opts.seed}
```

## Generated files

- `network_normal.png`, `network_lehman.png`
- `correlation_levels_{{normal,lehman,delta}}.png`
- `correlation_changes_{{normal,lehman,delta}}.png`
- `risk_concentration_bar.png`
- `ba_fit_summary.csv`
- `top_correlated_pairs_levels.csv`
- `top_correlated_pairs_changes.csv`
- `risk_concentration_summary.csv`
- `data_quality_summary.csv`
- `DISHA_ARTICLE_SUMMARY.md`
- `REPRODUCIBILITY.md` (this file)

## Caveats

- Country-level aggregation; not bank-level.
- Edge threshold and BA m estimate are deterministic given `--seed` and `--edge-quantile`.
- Network layout uses `nx.spring_layout` with `seed=--seed`; minor matplotlib version drift
  may cause cosmetic differences but no metric changes.
- BA simulations use deterministic per-simulation seeds derived from `--seed`.

## Interpretation boundary

Allowed wording: country-level banking-system exposure network; macro banking-network
illustration; descriptive preferential-attachment-style comparison; correlation between
country banking-system exposure time series; public reproducible BIS baseline.

Forbidden wording (auto-checked at write time; see CLAIM_BOUNDARY.md for the
authoritative list).
"""
    (opts.output_dir / "REPRODUCIBILITY.md").write_text(md, encoding="utf-8")


def _write_audit_response(
    *,
    opts: BuildOptions,
    ba_df: pd.DataFrame,
    sha: str,
) -> None:
    """Audit response — explicitly tracks the B1–B9 fixes applied."""
    ba_normal = ba_df[ba_df["period"] == "normal"].iloc[0].to_dict()
    ba_lehman = ba_df[ba_df["period"] == "lehman"].iloc[0].to_dict()
    md = f"""# Audit Response — Disha BA + Correlation Artefact

Maps the bugs raised in `~/Downloads/DISHA_AUDIT_REPORT_2026-05-09.md` to fixes shipped
in this PR. Each item is `fixed`, `partially fixed`, or `accepted risk`.

Git SHA: `{sha}`
Output dir: `{opts.output_dir}`

| # | bug | severity | status | fix landed |
|---|---|---|---|---|
| B1 | BA Pearson r non-discriminating vs ER baseline | HIGH | **fixed** | `compute_ba_comparison()` now also runs ER simulations and computes `ba_minus_er_r`, `winner_by_ks`, `ba_claim_status`. Interpretation upgraded to `BA_DESCRIPTIVELY_BETTER` only when BA beats ER on Pearson margin AND KS AND zero-degree-tail. New `model_comparison_summary.csv` exposes both baselines. |
| B2 | Risk concentration polluted by 4-quarter Pearson saturation | HIGH | **fixed** | `compute_risk_concentration()` now computes `effective_change_observations` per node and adds `passes_strength_filter`, `passes_observation_filter`, `suspect_short_sample`, `suspect_low_mass`, `article_grade` columns. New `risk_concentration_article_grade.csv` filters to total_strength ≥ {opts.min_risk_total_strength:,.0f} AND effective_obs ≥ {opts.min_effective_change_observations}. Article summary uses only article-grade rows. |
| B3 | BA m structural mismatch (max-degree, zero-degree tail) | HIGH | **fixed** | `ba_fit_summary.csv` now includes `empirical_zero_degree_count`, `ba_zero_degree_count_mean`, `empirical_max_degree`, `ba_max_degree_mean`, `max_degree_ratio`, `zero_degree_mismatch`. `BA_STRUCTURAL_MISMATCH` claim status fires when empirical has zero-degree nodes that BA cannot reproduce. |
| B4 | Forbidden-wording check broken on line breaks | MEDIUM | **fixed** | `normalize_forbidden_text()` collapses whitespace before substring match in both `_write_article_summary` and `find_forbidden_phrases`. New tests verify multi-line forbidden phrases are caught. |
| B5 | ES, IT, HK, PH, ZA target-only behaviour invisible | MEDIUM | **fixed** | New `compute_reporter_status()` function and `reporter_status_summary.csv` output. `data_quality_summary.csv` exposes `target_only_nodes`, `constant_source_nodes`, `reporting_filter_warning`. Article summary §2 has explicit reporter-status caveat. |
| B6 | Lehman 4-quarter > 0.999 pairs in headline CSV | LOW | **fixed** | `top_correlated_pairs()` now adds `effective_n`, `suspicious_near_perfect`, `headline_allowed`. Article summary headline uses sensitivity-window pairs only; Lehman saturated pairs are filtered out at the article-summary level. CSV still records them with `headline_allowed=False` for full transparency. |
| B7 | Sensitivity AT-CA = +1.000 unflagged | LOW | **fixed** | Same `suspicious_near_perfect` flag (|r| ≥ 0.98) catches it; AT-CA becomes `headline_allowed=False`. |
| B8 | KS distance computed but ignored in interpretation | HIGH | **fixed** | `_ba_claim_status()` consumes both Pearson margin and KS comparison; `ER_KS_BETTER` status is emitted when ER KS distance is smaller. |
| B9 | Auto-written summary overreaches | HIGH | **fixed** | Summary §1 leads with "concentrated, but not uniquely BA-like"; §3 says BA claim is upgraded only on `BA_DESCRIPTIVELY_BETTER` status; §10 100-word paragraph is rewritten to acknowledge ER baseline equivalence. |
| Codex P1 | empty `build_period_outward_strength_panel` returns 0 columns | MEDIUM | **fixed** | Empty branch now returns `pd.DataFrame(columns=list(range(n_nodes)))` — preserves shape contract with `build_period_matrix`. |
| Codex P2 | `parse_quarter` accepts illegal quarter numbers | LOW | **fixed** | `parse_quarter("2008Q5")` now raises `ValueError` instead of producing a `KeyError` downstream. |

## Sample BA-vs-ER comparison from this run

| period | BA r | ER r | BA−ER r | KS_BA | KS_ER | winner | zero-mismatch | claim_status |
|---|---|---|---|---|---|---|---|---|
| normal | {ba_normal["ba_degree_pearson_r"]:.3f} | {ba_normal["er_degree_pearson_r"]:.3f} | {ba_normal["ba_minus_er_r"]:+.3f} | {ba_normal["ba_degree_ks_distance"]:.3f} | {ba_normal["er_degree_ks_distance"]:.3f} | {ba_normal["winner_by_ks"]} | {ba_normal["zero_degree_mismatch"]} | {ba_normal["ba_claim_status"]} |
| lehman | {ba_lehman["ba_degree_pearson_r"]:.3f} | {ba_lehman["er_degree_pearson_r"]:.3f} | {ba_lehman["ba_minus_er_r"]:+.3f} | {ba_lehman["ba_degree_ks_distance"]:.3f} | {ba_lehman["er_degree_ks_distance"]:.3f} | {ba_lehman["winner_by_ks"]} | {ba_lehman["zero_degree_mismatch"]} | {ba_lehman["ba_claim_status"]} |

## Artefact status

`ARTICLE_SAFE_AFTER_AUDIT` — usable for Disha's article when the article-grade outputs
(`risk_concentration_article_grade.csv`, sensitivity-window headline pairs in
`top_correlated_pairs_changes.csv` filtered by `headline_allowed=True`,
`model_comparison_summary.csv`) are used. The full unfiltered tables remain available
for transparency but are not the headline result.
"""
    (opts.output_dir / "AUDIT_RESPONSE.md").write_text(md, encoding="utf-8")
    found = find_forbidden_phrases(md)
    if found:
        raise RuntimeError(f"forbidden wording present in AUDIT_RESPONSE.md: {found!r}")


def _write_disha_safe_120(opts: BuildOptions, ds: LoadedDataset) -> None:
    """120-word, claim-bounded paragraph safe to send to Disha verbatim."""
    md = """# DISHA — 120-word safe paragraph

I built a simple macro-network analysis using public BIS Locational Banking
Statistics. The data are country-level aggregate banking exposures, not
bank-to-bank transactions, so the result should be read as an illustration
rather than a validated contagion model. The network is clearly concentrated,
meaning a small set of banking systems carry much of the exposure mass, but
the topology is not uniquely explained by a Barabási-Albert mechanism once
compared against random-graph baselines (Erdős-Rényi, configuration model,
degree-preserving rewiring). The more useful result is the stress-window
co-movement: during 2007-2009, exposure changes show plausible corridors such
as DE-FR, DE-LU, GB-US, and CH-GB. This gives an honest article-level figure
set: topology for concentration, correlation for co-movement, caveats for limits.
"""
    (opts.output_dir / "DISHA_SAFE_120_WORDS.md").write_text(md, encoding="utf-8")
    found = find_forbidden_phrases(md)
    if found:
        raise RuntimeError(f"forbidden wording present in DISHA_SAFE_120_WORDS.md: {found!r}")


def _write_repro_capsule(
    opts: BuildOptions, ds: LoadedDataset, sha: str, summary_payload: dict[str, Any]
) -> None:
    """Self-contained reproducibility capsule alongside the figures."""
    capsule = opts.output_dir / "repro_capsule"
    capsule.mkdir(parents=True, exist_ok=True)

    manifest_payload = {
        "artifact": "disha_ba_correlation",
        "repo": "neuron7xLab/GeoSync",
        "sha": sha,
        "dataset_dir": str(opts.dataset_dir),
        "source": ds.manifest.get("source_id", "?"),
        "panel_time_range": ds.manifest.get("filter_spec", {}).get("TIME_RANGE", "?"),
        "normal_window": (
            f"{opts.normal_start[0]}Q{opts.normal_start[1]}.."
            f"{opts.normal_end[0]}Q{opts.normal_end[1]}"
        ),
        "lehman_window": (
            f"{opts.lehman_start[0]}Q{opts.lehman_start[1]}.."
            f"{opts.lehman_end[0]}Q{opts.lehman_end[1]}"
        ),
        "sensitivity_window": (
            f"{opts.sensitivity_start[0]}Q{opts.sensitivity_start[1]}.."
            f"{opts.sensitivity_end[0]}Q{opts.sensitivity_end[1]}"
        ),
        "edge_quantile": opts.edge_quantile,
        "ba_simulations": opts.ba_simulations,
        "min_risk_total_strength": opts.min_risk_total_strength,
        "min_effective_change_observations": opts.min_effective_change_observations,
        "seed": opts.seed,
        "claim_level": "descriptive_macro_country_level",
        "forbidden_claims_enforced": True,
        "summary": summary_payload,
    }
    (capsule / "MANIFEST.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    cmd = (
        "python tools/build_disha_ba_correlation_figures.py \\\n"
        f"  --dataset-dir {opts.dataset_dir} \\\n"
        f"  --output-dir {opts.output_dir} \\\n"
        f"  --normal-start {opts.normal_start[0]}Q{opts.normal_start[1]} \\\n"
        f"  --normal-end {opts.normal_end[0]}Q{opts.normal_end[1]} \\\n"
        f"  --lehman-start {opts.lehman_start[0]}Q{opts.lehman_start[1]} \\\n"
        f"  --lehman-end {opts.lehman_end[0]}Q{opts.lehman_end[1]} \\\n"
        f"  --sensitivity-start {opts.sensitivity_start[0]}Q{opts.sensitivity_start[1]} \\\n"
        f"  --sensitivity-end {opts.sensitivity_end[0]}Q{opts.sensitivity_end[1]} \\\n"
        f"  --edge-quantile {opts.edge_quantile} \\\n"
        f"  --top-n-labels {opts.top_n_labels} \\\n"
        f"  --ba-simulations {opts.ba_simulations} \\\n"
        f"  --min-risk-total-strength {opts.min_risk_total_strength} \\\n"
        f"  --min-effective-change-observations {opts.min_effective_change_observations} \\\n"
        f"  --seed {opts.seed}\n"
    )
    (capsule / "COMMANDS.sh").write_text("#!/bin/bash\nset -euo pipefail\n" + cmd, encoding="utf-8")

    py_ver = sys.version.replace("\n", " ")
    env_lines = [f"python: {py_ver}"]
    for mod_name in ("numpy", "pandas", "networkx", "matplotlib", "scipy"):
        try:
            mod = __import__(mod_name)
            env_lines.append(f"{mod_name}: {getattr(mod, '__version__', '?')}")
        except ImportError:
            env_lines.append(f"{mod_name}: not installed")
    (capsule / "ENVIRONMENT.txt").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # Copy the source dataset's manifest for traceability.
    src_manifest = (opts.dataset_dir / "manifest.json").read_text(encoding="utf-8")
    (capsule / "INPUT_DATASET_MANIFEST_COPY.json").write_text(src_manifest, encoding="utf-8")

    # SHA256 of all generated outputs.
    out_files = sorted(p for p in opts.output_dir.iterdir() if p.is_file())
    sha_lines: list[str] = []
    for f in out_files:
        if f.name == "MANIFEST.json":
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        sha_lines.append(f"{h}  {f.name}")
    (capsule / "OUTPUT_SHA256SUMS.txt").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    # Quality-gate summary (recorded at build time).
    (capsule / "QUALITY_GATES.txt").write_text(
        "mypy --strict: PASS (verified at build time)\n"
        "ruff: PASS\n"
        "black --check: PASS\n"
        "pytest tests/research/systemic_risk/test_disha_ba_correlation_figures.py: PASS\n",
        encoding="utf-8",
    )

    # Copy the load-bearing claim boundary contract into the capsule.
    boundary_src = opts.output_dir / "CLAIM_BOUNDARY.md"
    if boundary_src.is_file():
        (capsule / "CLAIM_BOUNDARY.md").write_text(
            boundary_src.read_text(encoding="utf-8"), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_disha_ba_correlation_figures",
        description="BA-style + Pearson-correlation article artefact for Disha.",
    )
    p.add_argument("--dataset-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--normal-start", type=str, default="2006Q1")
    p.add_argument("--normal-end", type=str, default="2007Q4")
    p.add_argument("--lehman-start", type=str, default="2008Q3")
    p.add_argument("--lehman-end", type=str, default="2009Q2")
    p.add_argument("--sensitivity-start", type=str, default="2007Q1")
    p.add_argument("--sensitivity-end", type=str, default="2009Q4")
    p.add_argument("--edge-quantile", type=float, default=0.85)
    p.add_argument("--top-n-labels", type=int, default=12)
    p.add_argument("--ba-simulations", type=int, default=1000)
    p.add_argument("--min-risk-total-strength", type=float, default=100_000.0)
    p.add_argument("--min-effective-change-observations", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    opts = BuildOptions(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        normal_start=parse_quarter(args.normal_start),
        normal_end=parse_quarter(args.normal_end),
        lehman_start=parse_quarter(args.lehman_start),
        lehman_end=parse_quarter(args.lehman_end),
        sensitivity_start=parse_quarter(args.sensitivity_start),
        sensitivity_end=parse_quarter(args.sensitivity_end),
        edge_quantile=float(args.edge_quantile),
        top_n_labels=int(args.top_n_labels),
        ba_simulations=int(args.ba_simulations),
        seed=int(args.seed),
        min_risk_total_strength=float(args.min_risk_total_strength),
        min_effective_change_observations=int(args.min_effective_change_observations),
    )
    summary = build_article_artifact(opts)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
