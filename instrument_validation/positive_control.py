# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Positive-control validation for the BA-mechanism scoring instrument.

Five injection protocols generate synthetic substrates with KNOWN
ground-truth mechanism. The instrument under test must achieve power
≥ 0.80 against AT LEAST ONE BA_vs_* contrast AND keep FPR ≤ 0.05 on
ER and CM.

The expected (preregistered) result on N=31 BIS-LBS-cadence substrates
is that ``sorted_degree_pearson`` FAILS this gate. That outcome is the
correct verdict; do not retune the metric to pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import networkx as nx
import numpy as np


class _ScoreFn(Protocol):
    """Callable that maps an undirected adjacency matrix to a scalar."""

    def __call__(self, adjacency: np.ndarray) -> float: ...


_N_DEFAULT: int = 31
_N_RUNS_DEFAULT: int = 500
_POWER_THRESHOLD: float = 0.80
_FPR_THRESHOLD: float = 0.05


# ---------------------------------------------------------------------------
# Injection protocols (named, parameterised by N=31)
# ---------------------------------------------------------------------------


def inject_ba(seed: int, n: int = _N_DEFAULT, m: int = 2) -> np.ndarray:
    g = nx.barabasi_albert_graph(n, m, seed=seed)
    return _to_adj(g, n)


def inject_er(seed: int, n: int = _N_DEFAULT, n_edges: int = 72) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = (2.0 * n_edges) / (n * (n - 1)) if n >= 2 else 0.0
    g = nx.gnp_random_graph(n, p, seed=int(rng.integers(0, 2**31 - 1)))
    return _to_adj(g, n)


def inject_cm(seed: int, n: int = _N_DEFAULT, m: int = 2) -> np.ndarray:
    """Configuration model with same expected mean degree as BA(n, m)."""
    rng = np.random.default_rng(seed)
    deg_template = sorted(
        nx.barabasi_albert_graph(n, m, seed=int(rng.integers(0, 2**31 - 1))).degree(),
        key=lambda x: -x[1],
    )
    deg = [d for _, d in deg_template]
    g = nx.configuration_model(deg, seed=int(rng.integers(0, 2**31 - 1)))
    g = nx.Graph(g)
    g.remove_edges_from(nx.selfloop_edges(g))
    return _to_adj(g, n)


def inject_hub(seed: int, n: int = _N_DEFAULT) -> np.ndarray:
    """1 super-hub deg≈19, ~22 mid-deg 8±2, ~7 zero-degree.

    Empirical Lehman skeleton; deliberately non-BA to test specificity.
    """
    rng = np.random.default_rng(seed)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    hub = 0
    n_mid = 22
    targets = list(range(1, n_mid + 1))
    rng.shuffle(targets)
    for t in targets[:19]:
        g.add_edge(hub, t)
    for i in range(1, n_mid + 1):
        cur_deg = g.degree(i)
        target_deg = max(0, int(rng.normal(8, 2)) - cur_deg)
        partners = [j for j in range(1, n_mid + 1) if j != i and not g.has_edge(i, j)]
        rng.shuffle(partners)
        for j in partners[:target_deg]:
            g.add_edge(i, j)
    # nodes [n_mid+1 .. n-1] stay isolated (zero-degree tail)
    return _to_adj(g, n)


def inject_gini(seed: int, n: int = _N_DEFAULT, n_edges: int = 72) -> np.ndarray:
    """Concentration matched on Gini(strength), independent of BA mechanism.

    Builds an exponentially-weighted random graph: choose edges so that
    weighted out-strength has a heavy-tailed distribution but the
    underlying generator is NOT preferential attachment.
    """
    rng = np.random.default_rng(seed)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    weights = np.exp(rng.normal(0.0, 1.5, n))
    weights = weights / weights.sum()
    edges_added: set[tuple[int, int]] = set()
    while len(edges_added) < n_edges:
        i, j = rng.choice(n, size=2, replace=False, p=weights)
        a, b = (int(i), int(j)) if i < j else (int(j), int(i))
        if a != b and (a, b) not in edges_added:
            edges_added.add((a, b))
            g.add_edge(a, b)
    return _to_adj(g, n)


_INJECTORS: dict[str, Callable[..., np.ndarray]] = {
    "BA": inject_ba,
    "ER": inject_er,
    "CM": inject_cm,
    "HUB": inject_hub,
    "GINI": inject_gini,
}


def _to_adj(g: Any, n: int) -> np.ndarray:
    a = np.zeros((n, n), dtype=np.uint8)
    for u, v in g.edges():
        if u != v:
            a[u, v] = 1
            a[v, u] = 1
    return a


# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PosControlCertificate:
    instrument_id: str
    n_runs: int
    detection_power: dict[str, float]  # 'BA_vs_ER', 'BA_vs_CM', 'BA_vs_HUB', 'BA_vs_GINI'
    false_positive_rate: dict[str, float]  # 'ER', 'CM'
    passed: bool
    failure_reason: str | None
    cert_id: str

    def is_valid_for(self, instrument_id: str) -> bool:
        return self.instrument_id == instrument_id and self.passed


def _two_sample_separation_power(
    score_a: np.ndarray, score_b: np.ndarray, alpha: float = 0.05
) -> float:
    """Empirical fraction of (a, b) pairs where score_a > score_b at α.

    For each run i, construct the null distribution from the other class
    and check if score_a[i] sits above the (1-α) quantile of score_b.
    """
    if score_a.size == 0 or score_b.size == 0:
        return 0.0
    threshold = float(np.percentile(score_b, 100.0 * (1 - alpha)))
    return float((score_a > threshold).sum() / score_a.size)


def validate_instrument(
    score_fn: _ScoreFn,
    *,
    instrument_id: str,
    n_runs: int = _N_RUNS_DEFAULT,
    seed: int = 42,
    n: int = _N_DEFAULT,
    power_threshold: float = _POWER_THRESHOLD,
    fpr_threshold: float = _FPR_THRESHOLD,
) -> PosControlCertificate:
    """Compute power vs ER/CM/HUB/GINI and FPR on ER/CM."""
    rng_master = np.random.default_rng(seed)

    def _scores(injector: Callable[..., np.ndarray], offset: int) -> np.ndarray:
        out = np.zeros(n_runs, dtype=np.float64)
        for k in range(n_runs):
            adj = injector(seed=int(rng_master.integers(0, 2**31 - 1)), n=n)
            out[k] = float(score_fn(adj))
        _ = offset
        return out

    ba_scores = _scores(inject_ba, 0)
    er_scores = _scores(inject_er, 1)
    cm_scores = _scores(inject_cm, 2)
    hub_scores = _scores(inject_hub, 3)
    gini_scores = _scores(inject_gini, 4)

    power = {
        "BA_vs_ER": _two_sample_separation_power(ba_scores, er_scores),
        "BA_vs_CM": _two_sample_separation_power(ba_scores, cm_scores),
        "BA_vs_HUB": _two_sample_separation_power(ba_scores, hub_scores),
        "BA_vs_GINI": _two_sample_separation_power(ba_scores, gini_scores),
    }
    # FPR — under the null (ER/CM) how often does the instrument call BA?
    ba_threshold = float(np.percentile(ba_scores, 5.0))  # bottom-5 of BA = liberal cutoff
    fpr = {
        "ER": float((er_scores >= ba_threshold).sum() / er_scores.size),
        "CM": float((cm_scores >= ba_threshold).sum() / cm_scores.size),
    }
    any_power_ok = any(p >= power_threshold for p in power.values())
    all_fpr_ok = all(f <= fpr_threshold for f in fpr.values())
    passed = any_power_ok and all_fpr_ok
    if not any_power_ok:
        reason: str | None = (
            f"detection_power < {power_threshold} on every BA_vs_* contrast: {power}"
        )
    elif not all_fpr_ok:
        reason = f"false_positive_rate > {fpr_threshold} on at least one null: {fpr}"
    else:
        reason = None
    cert_payload = (
        f"{instrument_id}|{n_runs}|{seed}|power={sorted(power.items())}|fpr={sorted(fpr.items())}"
    )
    cert_id = hashlib.sha256(cert_payload.encode("utf-8")).hexdigest()
    return PosControlCertificate(
        instrument_id=instrument_id,
        n_runs=int(n_runs),
        detection_power=power,
        false_positive_rate=fpr,
        passed=bool(passed),
        failure_reason=reason,
        cert_id=cert_id,
    )
