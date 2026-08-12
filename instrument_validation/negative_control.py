# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-control validation — declared, finite null families.

The instrument must keep false-positive rate ≤ 0.05 on EVERY declared
null family. Closes B5 (constant-node trap) and B6/B7 (low-n Pearson
saturation) by promoting them to first-class nulls instead of after-
the-fact warnings.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Protocol

import networkx as nx
import numpy as np

REQUIRED_NULLS: tuple[str, ...] = (
    "erdos_renyi_density_matched",
    "configuration_model_uniform_double_swap",
    "low_n_correlation_saturation",
    "constant_node_zero_strength",
)

_FPR_THRESHOLD: float = 0.05
_MIN_RUNS_PER_FAMILY: int = 500


class _ScoreFn(Protocol):
    def __call__(self, adjacency: np.ndarray) -> float: ...


# ---------------------------------------------------------------------------
# Null generators
# ---------------------------------------------------------------------------


def gen_erdos_renyi(seed: int, n: int, n_edges: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = (2.0 * n_edges) / (n * (n - 1)) if n >= 2 else 0.0
    g = nx.gnp_random_graph(n, p, seed=int(rng.integers(0, 2**31 - 1)))
    return _to_adj(g, n)


def gen_configuration_double_swap(seed: int, n: int, degree_sequence: list[int]) -> np.ndarray:
    """Maslov-Sneppen 2002 — uniform sampler of graphs with given degree
    sequence via double-edge swaps."""
    rng = np.random.default_rng(seed)
    g = nx.configuration_model(degree_sequence, seed=int(rng.integers(0, 2**31 - 1)))
    g = nx.Graph(g)
    g.remove_edges_from(nx.selfloop_edges(g))
    n_edges = g.number_of_edges()
    nswap = max(5, n_edges // 2)
    max_tries = max(500, 100 * n_edges)
    if n_edges >= 2:
        try:
            nx.algorithms.swap.double_edge_swap(
                g, nswap=nswap, max_tries=max_tries, seed=int(rng.integers(0, 2**31 - 1))
            )
        except (nx.NetworkXError, nx.NetworkXAlgorithmError):
            pass
    return _to_adj(g, n)


def gen_low_n_correlation_pair(seed: int, n_obs: int = 3, n_pairs: int = 1) -> np.ndarray:
    """Sample n_obs random Pearson correlations on n_obs-point series.

    For n=3, almost any Pearson r is drawn from the full [-1,1] range —
    the saturation trap that produced |r|>0.999 in the original Lehman
    4-quarter window. Returns the absolute correlation as the "score".
    """
    rng = np.random.default_rng(seed)
    rs = np.zeros(n_pairs, dtype=np.float64)
    for k in range(n_pairs):
        x = rng.normal(size=n_obs)
        y = rng.normal(size=n_obs)
        if x.std() == 0 or y.std() == 0:
            rs[k] = float("nan")
        else:
            rs[k] = float(abs(np.corrcoef(x, y)[0, 1]))
    return rs[~np.isnan(rs)]


def gen_constant_node_panel(seed: int, n_nodes: int = 31, n_quarters: int = 8) -> np.ndarray:
    """Mostly-zero outgoing-strength panel that mirrors the BIS reporter
    suppression pattern (ES, IT, HK, PH, ZA: zero out-strength every quarter
    under the active filter). Tests whether the score function survives
    this NaN-density without producing false-positive flags.
    """
    rng = np.random.default_rng(seed)
    arr = np.zeros((n_quarters, n_nodes), dtype=np.float64)
    # 5 zero-strength reporter slots + rest randomly populated
    populated = list(range(n_nodes))
    rng.shuffle(populated)
    zero_idx = set(populated[:5])
    for j in range(n_nodes):
        if j in zero_idx:
            continue
        arr[:, j] = rng.lognormal(mean=10.0, sigma=1.0, size=n_quarters)
    return arr


def _to_adj(g: nx.Graph, n: int) -> np.ndarray:
    a = np.zeros((n, n), dtype=np.uint8)
    for u, v in g.edges():
        if u != v:
            a[u, v] = 1
            a[v, u] = 1
    return a


# ---------------------------------------------------------------------------
# Negative-control runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NegativeControlCertificate:
    instrument_id: str
    n_runs_per_family: int
    fpr_per_family: dict[str, float]
    max_observed_fpr: float
    families: tuple[str, ...]
    passed: bool
    failure_reason: str | None
    cert_id: str

    def is_valid_for(self, instrument_id: str) -> bool:
        return self.instrument_id == instrument_id and self.passed


def run_negative_controls(
    score_fn: _ScoreFn,
    *,
    instrument_id: str,
    n_runs: int = _MIN_RUNS_PER_FAMILY,
    n: int = 31,
    n_edges: int = 72,
    seed: int = 42,
    decision_threshold: float | None = None,
    decision_fn: Callable[[float], bool] | None = None,
    fpr_threshold: float = _FPR_THRESHOLD,
) -> NegativeControlCertificate:
    """Compute FPR on every declared null family.

    ``decision_fn`` is the function that converts a score to a positive
    BA-claim flag. If None, the instrument is treated as a numeric score
    and ``decision_threshold`` is used as ``score > threshold ⇒ positive``.
    """
    if n_runs < _MIN_RUNS_PER_FAMILY:
        raise ValueError(f"n_runs={n_runs} < required {_MIN_RUNS_PER_FAMILY} per family")
    if decision_fn is None:
        threshold = 0.0 if decision_threshold is None else float(decision_threshold)

        def _default_decision(score: float, _t: float = threshold) -> bool:
            return bool(score > _t)

        decision_fn = _default_decision

    rng_master = np.random.default_rng(seed)
    fpr: dict[str, float] = {}

    # 1. Erdős-Rényi density-matched
    pos = 0
    for _ in range(n_runs):
        adj = gen_erdos_renyi(int(rng_master.integers(0, 2**31 - 1)), n, n_edges)
        if decision_fn(float(score_fn(adj))):
            pos += 1
    fpr["erdos_renyi_density_matched"] = float(pos / n_runs)

    # 2. Configuration model with double-swap (uses BA m=2 degree as template)
    template = sorted(
        nx.barabasi_albert_graph(n, max(1, n_edges // n), seed=42).degree(),
        key=lambda x: -x[1],
    )
    deg_seq = [d for _, d in template]
    pos = 0
    for _ in range(n_runs):
        adj = gen_configuration_double_swap(int(rng_master.integers(0, 2**31 - 1)), n, deg_seq)
        if decision_fn(float(score_fn(adj))):
            pos += 1
    fpr["configuration_model_uniform_double_swap"] = float(pos / n_runs)

    # 3. Low-n correlation saturation — for each saturated 3-point pair
    #    build the implied 2-node "co-movement" adjacency and route
    #    through score_fn + decision_fn so the FPR measures whether the
    #    analyst's pipeline (not the saturation itself) emits BA-positive.
    saturated = gen_low_n_correlation_pair(
        int(rng_master.integers(0, 2**31 - 1)), n_obs=3, n_pairs=n_runs
    )
    pos = 0
    triggered = saturated[saturated >= 0.95]
    for _ in triggered:
        adj = np.array([[0, 1], [1, 0]], dtype=np.uint8)
        if decision_fn(float(score_fn(adj))):
            pos += 1
    denom = max(saturated.size, 1)
    fpr["low_n_correlation_saturation"] = float(pos / denom)

    # 4. Constant-node panel — score must not flag spurious co-movement
    pos = 0
    for _ in range(n_runs):
        panel = gen_constant_node_panel(int(rng_master.integers(0, 2**31 - 1)), n_nodes=n)
        # Wrap as adjacency-style proxy: treat |corr matrix| max off-diag.
        if panel.std() == 0:
            continue
        with np.errstate(invalid="ignore"):
            cor = np.corrcoef(panel, rowvar=False)
        cor = np.where(np.isnan(cor), 0.0, cor)
        adj = (np.abs(cor) >= 0.5).astype(np.uint8)
        np.fill_diagonal(adj, 0)
        if decision_fn(float(score_fn(adj))):
            pos += 1
    fpr["constant_node_zero_strength"] = float(pos / n_runs)

    max_fpr = max(fpr.values())
    passed = max_fpr <= fpr_threshold
    if not passed:
        worst = max(fpr.items(), key=lambda kv: kv[1])
        reason: str | None = (
            f"max false-positive rate {max_fpr:.3f} > {fpr_threshold} "
            f"(worst null: {worst[0]}={worst[1]:.3f})"
        )
    else:
        reason = None
    cert_payload = f"{instrument_id}|{n_runs}|{seed}|fpr={sorted(fpr.items())}"
    cert_id = hashlib.sha256(cert_payload.encode("utf-8")).hexdigest()
    return NegativeControlCertificate(
        instrument_id=instrument_id,
        n_runs_per_family=int(n_runs),
        fpr_per_family=fpr,
        max_observed_fpr=float(max_fpr),
        families=REQUIRED_NULLS,
        passed=bool(passed),
        failure_reason=reason,
        cert_id=cert_id,
    )
