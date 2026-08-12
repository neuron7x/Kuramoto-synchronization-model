# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G2 — validate_instrument refuses cert if detection_power < 0.80
on every BA_vs_* contrast. sorted_degree_pearson MUST fail this gate."""

from __future__ import annotations

import networkx as nx
import numpy as np

from instrument_validation.positive_control import (
    inject_ba,
    inject_cm,
    inject_er,
    inject_gini,
    inject_hub,
    validate_instrument,
)


def _sorted_degree_pearson(adjacency: np.ndarray) -> float:
    """The 'BA-similar' candidate from the Disha audit. Compares empirical
    sorted degree to a single BA(N=31, m=2) reference sorted degree."""
    n = int(adjacency.shape[0])
    sym = ((adjacency + adjacency.T) > 0).astype(np.uint8)
    np.fill_diagonal(sym, 0)
    deg_emp = np.sort(sym.sum(axis=1))[::-1].astype(np.float64)
    g_ref = nx.barabasi_albert_graph(n, 2, seed=0)
    deg_ref = np.array(sorted(dict(g_ref.degree()).values(), reverse=True), dtype=np.float64)
    if deg_emp.std() == 0 or deg_ref.std() == 0:
        return 0.0
    return float(np.corrcoef(deg_emp, deg_ref)[0, 1])


def test_injectors_produce_correct_node_count() -> None:
    for fn in (inject_ba, inject_er, inject_cm, inject_hub, inject_gini):
        adj = fn(seed=42)
        assert adj.shape == (31, 31)
        # symmetric, zero diagonal
        assert np.array_equal(adj, adj.T)
        assert np.all(np.diag(adj) == 0)


def test_validate_instrument_refuses_cert_for_sorted_degree_pearson() -> None:
    """G2: sorted_degree_pearson must NOT receive a valid cert at N=31.

    Run with reduced n_runs for test speed; the gate logic is what matters.
    """
    cert = validate_instrument(
        _sorted_degree_pearson,
        instrument_id="sorted_degree_pearson@v0",
        n_runs=80,
        seed=42,
    )
    assert not cert.passed, (
        "sorted_degree_pearson must FAIL positive control at N=31 — "
        f"got passed=True with power={cert.detection_power}"
    )
    assert cert.failure_reason is not None
    assert cert.cert_id  # non-empty hex


def test_validate_instrument_records_all_four_contrasts() -> None:
    cert = validate_instrument(
        _sorted_degree_pearson,
        instrument_id="x",
        n_runs=50,
        seed=0,
    )
    for k in ("BA_vs_ER", "BA_vs_CM", "BA_vs_HUB", "BA_vs_GINI"):
        assert k in cert.detection_power
    for k in ("ER", "CM"):
        assert k in cert.false_positive_rate
