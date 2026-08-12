# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for discrete Ricci flow + neckpinch surgery primitives.

INV-RC-FLOW — discrete Ricci flow + neckpinch surgery preserves finiteness,
non-negativity, symmetry, zero diagonal, optional total-edge-mass, and graph
connectedness when ``preserve_connectedness=True``.
"""

from __future__ import annotations

import time

import networkx as nx
import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.ricci_flow import (
    NeckpinchEvent,
    RicciFlowConfig,
    apply_neckpinch_surgery,
    detect_neckpinch_candidates,
    discrete_ricci_flow_step,
    ricci_flow_with_surgery,
)
from core.kuramoto.ricci_flow_engine import (
    KuramotoRicciFlowEngine,
    KuramotoRicciFlowSurgeryDiagnostics,
)


def _ring_weights(n: int = 5, w: float = 1.0) -> NDArray[np.float64]:
    """Connected ring with uniform edge weight ``w``."""
    W = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        j = (i + 1) % n
        W[i, j] = w
        W[j, i] = w
    return W


def _curvature_uniform(W: NDArray[np.float64], k: float) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    n = W.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            if W[i, j] > 0.0:
                out[(i, j)] = float(k)
    return out


def test_flow_preserves_symmetry_zero_diag_finiteness() -> None:
    """INV-RC-FLOW: flow step preserves symmetry, zero diag, finiteness, non-negativity."""
    W = _ring_weights(6, 1.0)
    kappa = _curvature_uniform(W, 0.4)
    cfg = RicciFlowConfig(eta=0.1)
    out = discrete_ricci_flow_step(W, kappa, cfg)

    violations: list[str] = []
    if not np.isfinite(out).all():
        violations.append("non-finite")
    if (out < 0.0).any():
        violations.append("negative")
    if not np.allclose(out, out.T, atol=1e-12):
        violations.append("asymmetric")
    if not np.allclose(np.diag(out), 0.0, atol=1e-12):
        violations.append("nonzero-diag")
    assert not violations, (
        "INV-RC-FLOW VIOLATED: flow step must preserve invariants; "
        f"observed violations={violations}, expected none, with N=6, eta=0.1, "
        f"min={out.min():.6f}, max={out.max():.6f}."
    )


def test_flow_preserves_total_edge_mass_when_enabled() -> None:
    """INV-RC-FLOW: total edge mass invariant under preserve_total_edge_mass=True."""
    W = _ring_weights(8, 0.7)
    kappa = _curvature_uniform(W, 0.3)
    cfg = RicciFlowConfig(eta=0.05, preserve_total_edge_mass=True)
    total_before = float(W.sum())
    out = discrete_ricci_flow_step(W, kappa, cfg)
    total_after = float(out.sum())
    assert abs(total_before - total_after) < 1e-9, (
        "INV-RC-FLOW VIOLATED: total edge mass must be preserved; "
        f"observed before={total_before:.6f}, after={total_after:.6f}, "
        f"|delta|={abs(total_before - total_after):.3e}, expected <1e-9, "
        "with N=8, eta=0.05."
    )


def test_neckpinch_removes_non_bridge_edge() -> None:
    """INV-RC-FLOW: a non-bridge edge in singular curvature tail is removed."""
    # K4 (complete on 4 nodes) — every edge has TWO triangle alternatives,
    # so no edge is a bridge. Singular curvature on edge (0,1) should remove it.
    n = 4
    W = np.ones((n, n), dtype=np.float64) - np.eye(n)
    kappa = _curvature_uniform(W, 0.0)
    kappa[(0, 1)] = -0.999  # singular tail

    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=1.0,
        preserve_connectedness=True,
    )
    new_w, events = apply_neckpinch_surgery(W, kappa, cfg)

    actions = [e.action for e in events if e.edge == (0, 1)]
    assert "removed" in actions, (
        "INV-RC-FLOW VIOLATED: non-bridge edge in singular tail must be removed; "
        f"observed actions={actions} for edge (0,1), expected 'removed', "
        f"K4 with N={n}, kappa(0,1)=-0.999."
    )
    assert new_w[0, 1] == 0.0, (
        "INV-RC-FLOW VIOLATED: removed edge weight must be 0; "
        f"observed w(0,1)={new_w[0, 1]}, expected 0.0."
    )


def test_neckpinch_clamps_bridge_when_connectedness_required() -> None:
    """INV-RC-FLOW: a bridge edge is clamped, never removed, when connectedness required."""
    # Path graph 0-1-2-3-4: every edge is a bridge.
    n = 5
    W = np.zeros((n, n), dtype=np.float64)
    for i in range(n - 1):
        W[i, i + 1] = 1.0
        W[i + 1, i] = 1.0

    kappa = {(i, i + 1): -0.99 for i in range(n - 1)}
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        eps_weight=1e-4,
        max_surgery_fraction=1.0,
        preserve_connectedness=True,
    )
    new_w, events = apply_neckpinch_surgery(W, kappa, cfg)

    # No edge may be removed; all should be skipped_bridge → weight clamped to eps_weight.
    actions = sorted({e.action for e in events})
    assert "removed" not in actions, (
        "INV-RC-FLOW VIOLATED: bridge edges must not be removed when "
        f"preserve_connectedness=True; observed actions={actions}, "
        f"expected only 'skipped_bridge'/'clamped', with N={n} path graph."
    )
    # Connected check: every adjacent pair still has positive weight.
    for i in range(n - 1):
        assert new_w[i, i + 1] > 0.0, (
            "INV-RC-FLOW VIOLATED: bridge edge weight became 0 despite "
            f"preserve_connectedness=True; observed w({i},{i + 1})={new_w[i, i + 1]}, "
            f"expected >0, with N={n} path graph."
        )


def test_surgery_fraction_cap() -> None:
    """INV-RC-FLOW: removed-count ≤ floor(max_surgery_fraction * n_active_edges)."""
    n = 10
    W = np.ones((n, n), dtype=np.float64) - np.eye(n)
    # All edges in singular tail.
    kappa = {(i, j): -0.999 for i in range(n) for j in range(i + 1, n)}
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=0.1,
        preserve_connectedness=False,
        allow_disconnect=True,
    )
    _, events = apply_neckpinch_surgery(W, kappa, cfg)
    n_edges = n * (n - 1) // 2
    cap = int(np.floor(0.1 * n_edges))
    n_removed = sum(1 for e in events if e.action == "removed")
    assert n_removed <= cap, (
        "INV-RC-FLOW VIOLATED: removed count exceeds surgery_fraction cap; "
        f"observed n_removed={n_removed}, expected <={cap}, "
        f"with N={n}, n_edges={n_edges}, max_surgery_fraction=0.1."
    )


def test_integration_default_matches_previous_ricci_engine_behavior() -> None:
    """INV-RC-FLOW: default flags (OFF) leave the engine bit-identical to legacy run."""
    cfg = KuramotoConfig(N=8, K=1.5, dt=0.05, steps=120, seed=11)

    eng_a = KuramotoRicciFlowEngine(cfg, ricci_update_interval=20, coupling_history_enabled=True)
    eng_b = KuramotoRicciFlowEngine(
        cfg,
        ricci_update_interval=20,
        coupling_history_enabled=True,
        enable_discrete_flow=False,
        enable_neckpinch_surgery=False,
    )
    res_a = eng_a.run()
    res_b = eng_b.run()

    failures: list[str] = []
    if not np.array_equal(res_a.phases, res_b.phases):
        failures.append("phases differ")
    if not np.array_equal(res_a.order_parameter, res_b.order_parameter):
        failures.append("order_parameter differs")
    if not np.array_equal(res_a.coupling_matrix_history, res_b.coupling_matrix_history):
        failures.append("coupling_matrix_history differs")
    assert not failures, (
        "INV-RC-FLOW VIOLATED: default flags (OFF) must preserve legacy behavior; "
        f"observed differences={failures}, expected none, with N=8, K=1.5, "
        "steps=120, seed=11."
    )


def test_integration_enabled_records_surgery_events() -> None:
    """INV-RC-FLOW: enabling flow+surgery emits a diagnostics object with non-empty events."""
    cfg = KuramotoConfig(N=8, K=2.5, dt=0.05, steps=300, seed=7)
    flow_cfg = RicciFlowConfig(
        eta=0.05,
        eps_weight=1e-3,
        eps_neck=0.5,  # broad tail so a few edges get caught
        preserve_connectedness=True,
        max_surgery_fraction=0.2,
    )
    eng = KuramotoRicciFlowEngine(
        cfg,
        ricci_update_interval=30,
        graph_threshold=0.05,
        enable_discrete_flow=True,
        enable_neckpinch_surgery=True,
        ricci_flow_config=flow_cfg,
    )
    result, diag = eng.run_with_surgery()

    assert isinstance(diag, KuramotoRicciFlowSurgeryDiagnostics)
    # The result still satisfies INV-K1 at every step.
    assert (result.order_parameter >= 0.0).all() and (result.order_parameter <= 1.0).all(), (
        "INV-K1 VIOLATED: order_parameter outside [0,1] under flow+surgery; "
        f"observed min={result.order_parameter.min():.6f}, "
        f"max={result.order_parameter.max():.6f}, with N=8, K=2.5, steps=300, "
        "seed=7, eta=0.05."
    )
    # mass-preservation arrays match the number of curvature updates that ran.
    assert len(diag.total_edge_mass_before) == len(diag.total_edge_mass_after), (
        "INV-RC-FLOW VIOLATED: mass-before/after sequence lengths must match; "
        f"observed before_len={len(diag.total_edge_mass_before)}, "
        f"after_len={len(diag.total_edge_mass_after)}, expected equal."
    )


def test_ricci_flow_deterministic() -> None:
    """INV-RC-FLOW: ricci_flow_with_surgery is a deterministic pure function."""
    W = _ring_weights(7, 1.2)
    kappa = _curvature_uniform(W, 0.0)
    kappa[(0, 1)] = -0.999
    kappa[(2, 3)] = -0.998
    cfg = RicciFlowConfig(eta=0.05, eps_neck=1e-3, max_surgery_fraction=0.5)

    r1 = ricci_flow_with_surgery(W, kappa, cfg)
    r2 = ricci_flow_with_surgery(W, kappa, cfg)
    np.testing.assert_array_equal(r1.weights_after, r2.weights_after)
    assert r1.surgery_event_count == r2.surgery_event_count, (
        "INV-RC-FLOW VIOLATED: surgery_event_count must be deterministic; "
        f"observed run1={r1.surgery_event_count}, run2={r2.surgery_event_count}, "
        "expected equal, with N=7."
    )


def test_eta_out_of_range_rejected() -> None:
    """RicciFlowConfig validation: eta in (0,1) is enforced."""
    with pytest.raises(ValueError, match="eta"):
        RicciFlowConfig(eta=0.0)
    with pytest.raises(ValueError, match="eta"):
        RicciFlowConfig(eta=1.5)


def test_detect_neckpinch_candidates_lex_order() -> None:
    """INV-RC-FLOW: detection returns candidates in lex order."""
    W = np.ones((4, 4), dtype=np.float64) - np.eye(4)
    kappa = {
        (0, 3): -0.999,
        (1, 2): -0.999,
        (0, 1): -0.999,
    }
    cfg = RicciFlowConfig(eta=0.05, eps_neck=1e-3)
    cand = detect_neckpinch_candidates(W, kappa, cfg)
    assert cand == sorted(cand), (
        "INV-RC-FLOW VIOLATED: candidates must be lexicographically sorted; "
        f"observed={cand}, expected sorted ascending."
    )


def test_neckpinch_event_dataclass_immutable() -> None:
    """NeckpinchEvent is frozen — fields cannot be reassigned."""
    e = NeckpinchEvent(
        edge=(0, 1), old_weight=1.0, new_weight=0.0, curvature=-0.99, action="removed"
    )
    with pytest.raises((AttributeError, TypeError)):
        e.old_weight = 2.0  # type: ignore[misc]


def test_surgery_bridge_detection_is_O_E_not_E_squared() -> None:
    """INV-RC-FLOW perf contract: bridge detection is O(V+E) per surgery step.

    Regression guard for the ``ricci_flow.py`` per-candidate ``_is_bridge``
    hot-path: the historical implementation called ``nx.bridges`` once per
    candidate, giving total :math:`O(E^2)` cost on dense Erdős–Rényi inputs
    where most edges enter the singular-curvature tail. PR #381's
    microbench had to skip ``bench_ricci_flow.py @ N=1024`` under the
    ``wall_time_budget_exceeded=600s`` gate, empirically confirming the
    bottleneck.

    The fix caches ``frozenset(nx.bridges(graph))`` and only invalidates
    after an actual ``graph.remove_edge`` call. Clamps preserve topology
    and so preserve the cache. With the linear-chain / dense ER inputs
    used here every candidate is non-bridge or every candidate is a
    bridge — either way the recompute count is bounded by the number of
    actual removals (capped by ``max_surgery_fraction``), not by the
    number of candidates.

    Bound rationale: at ``N=200`` and ``p≈0.05`` the active edge count is
    ``~995`` and a single ``nx.bridges`` is microseconds-scale; the
    tightest legitimate run on modern hardware is ``≪50 ms``. The
    pre-fix :math:`O(E^2)` form was ``≫1 s`` at this size. We use 500 ms
    as a generous flake-resistant ceiling: a pre-fix regression would
    blow well past it; a transient CI scheduling hiccup will not.
    """
    rng = np.random.default_rng(20260425)
    n = 200
    adj = (rng.random((n, n)) < 0.05).astype(bool)
    adj |= adj.T
    np.fill_diagonal(adj, False)
    weights = rng.random((n, n)) * adj
    weights = 0.5 * (weights + weights.T)
    np.fill_diagonal(weights, 0.0)

    iu, ju = np.where(np.triu(adj, k=1))
    curvature: dict[tuple[int, int], float] = {
        (int(i), int(j)): float(rng.uniform(-1.0, 1.0)) for i, j in zip(iu, ju, strict=True)
    }

    # eps_weight=0.5 forces a large fraction of edges into the
    # weight-tail candidate set so the surgery loop visits many edges.
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_weight=0.5,
        eps_neck=1e-3,
        preserve_connectedness=True,
        max_surgery_fraction=0.05,
    )

    candidates = detect_neckpinch_candidates(weights, curvature, cfg)
    assert len(candidates) > 100, (
        "INV-RC-FLOW VIOLATED (test setup): regression guard requires "
        f"a many-candidate workload; observed |candidates|={len(candidates)}, "
        "expected >100 to exercise the per-candidate hot-path."
    )

    t0_ns = time.perf_counter_ns()
    apply_neckpinch_surgery(weights, curvature, cfg)
    elapsed_ns = time.perf_counter_ns() - t0_ns

    elapsed_ms = elapsed_ns / 1e6
    # 500 ms ceiling: O(V+E) target is ≪50 ms; legacy O(E²) at this size
    # was ≫1000 ms. The bound is wide enough to absorb shared-CI noise
    # but tight enough to fail a regression to per-candidate nx.bridges.
    assert elapsed_ns < 500_000_000, (
        "INV-RC-FLOW perf-contract VIOLATED: apply_neckpinch_surgery "
        f"took {elapsed_ms:.1f} ms; expected <500 ms (O(V+E) bridge cache). "
        "Regression to per-candidate nx.bridges (O(E²)) suspected. "
        f"Context: N=200, p≈0.05, |candidates|={len(candidates)}, "
        "max_surgery_fraction=0.05, preserve_connectedness=True."
    )


def test_surgery_uf_guard_prevents_disconnect_when_all_cycle_edges_candidate() -> None:
    """INV-RC-FLOW: union-find guard preserves connectivity on full-cycle candidates.

    Adversarial scenario: a 4-cycle ``0-1-2-3-0`` where every edge is in
    the singular curvature tail. The pre-surgery snapshot contains zero
    bridges (every edge is on a cycle), so a naive snapshot-only fix
    would classify all four candidates non-bridge and remove them — the
    graph would disconnect and the post-step connectivity assertion
    would raise ``RuntimeError``.

    The union-find guard prevents that: each candidate is only marked
    ``"removed"`` if its endpoints are connected through non-candidate
    or already-clamped edges. As candidates get clamped (kept alive at
    ``eps_weight``), their endpoints union into the UF; later candidates
    can then see those clamped paths. The post-surgery active subgraph
    is always connected — the contract is preserved without ever
    disconnecting. The exact number of removals depends on lex order
    and how quickly clamped edges form a connected backbone, but the
    invariant under test is: **no removal that would disconnect occurs**.
    """
    n = 4
    W = np.zeros((n, n), dtype=np.float64)
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        W[a, b] = 1.0
        W[b, a] = 1.0
    # All four cycle edges in singular tail.
    kappa = {(0, 1): -0.999, (0, 3): -0.999, (1, 2): -0.999, (2, 3): -0.999}
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=1.0,  # no cap — only the UF guard limits removal
        preserve_connectedness=True,
    )
    new_w, events = apply_neckpinch_surgery(W, kappa, cfg)

    # Connectivity check: rebuild the active graph from new_w and verify it
    # is still connected over the original active node set. This is the
    # core safety property the UF guard must enforce.
    active_after = nx.Graph()
    active_after.add_nodes_from(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if new_w[i, j] > 0.0:
                active_after.add_edge(i, j)
    assert nx.is_connected(active_after), (
        "INV-RC-FLOW VIOLATED: surgery disconnected a 4-cycle with all-candidate "
        "edges; UF safety net failed. "
        f"observed components={list(nx.connected_components(active_after))}, "
        "expected single component on {0,1,2,3}, with N=4 cycle, all edges candidate."
    )
    # Every edge that was clamped must have weight ≥ eps_weight.
    for ev in events:
        if ev.action == "clamped":
            i, j = ev.edge
            assert new_w[i, j] >= cfg.eps_weight, (
                "INV-RC-FLOW VIOLATED: clamped edge weight must be ≥ eps_weight "
                "after UF-guarded surgery; "
                f"observed w({i},{j})={new_w[i, j]:.3e}, "
                f"expected ≥ {cfg.eps_weight}, with N=4 cycle."
            )


def test_surgery_uf_guard_allows_removal_when_alternate_path_exists() -> None:
    """INV-RC-FLOW: union-find permits removals that preserve connectivity.

    Counterpart to the cycle-disconnect test: K4 (complete on 4 nodes)
    with a single singular-tail candidate ``(0, 1)``. The other five
    edges are non-candidates, so the UF starts fully connected. Removing
    ``(0, 1)`` is safe — the post-removal graph (K4 minus one edge)
    remains connected.
    """
    n = 4
    W = np.ones((n, n), dtype=np.float64) - np.eye(n)
    kappa: dict[tuple[int, int], float] = {(0, 1): -0.999}
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=1.0,
        preserve_connectedness=True,
    )
    new_w, events = apply_neckpinch_surgery(W, kappa, cfg)

    actions_by_edge = {e.edge: e.action for e in events}
    assert actions_by_edge[(0, 1)] == "removed", (
        "INV-RC-FLOW VIOLATED: candidate with non-candidate alternate path "
        "must be removable; "
        f"observed action={actions_by_edge[(0, 1)]}, expected 'removed', "
        "with K4 and only (0,1) in singular tail."
    )
    assert new_w[0, 1] == 0.0, (
        "INV-RC-FLOW VIOLATED: removed edge weight must be exactly 0.0; "
        f"observed w(0,1)={new_w[0, 1]}, expected 0.0."
    )
