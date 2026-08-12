# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property tests for INV-RC-FLOW — discrete Ricci flow + neckpinch surgery.

INV-RC-FLOW: post-step weights are finite, non-negative, symmetric, zero
on the diagonal; total edge mass is preserved when enabled; bridges are
clamped (never removed) when ``preserve_connectedness=True``; surgery
removals are bounded by ``max_surgery_fraction``; every surgery decision
appears in the event log; zero curvature is a fixed point modulo float
noise.
"""

from __future__ import annotations

import numpy as np
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from core.kuramoto.ricci_flow import (
    RicciFlowConfig,
    apply_neckpinch_surgery,
    detect_neckpinch_candidates,
    discrete_ricci_flow_step,
    ricci_flow_with_surgery,
)

from .strategies import curvature_dicts, weight_matrices


def _bridge_chain(n: int, w: float = 1.0) -> NDArray[np.float64]:
    """Linear chain — every interior edge is a bridge."""
    W = np.zeros((n, n), dtype=np.float64)
    for i in range(n - 1):
        W[i, i + 1] = w
        W[i + 1, i] = w
    return W


def _check_weights_invariants(W: NDArray[np.float64], context: str) -> None:
    """INV-RC-FLOW: finite, non-negative, symmetric, zero-diagonal."""
    violations: list[str] = []
    if not np.isfinite(W).all():
        violations.append("non-finite")
    if (W < -1e-10).any():
        violations.append(f"negative (min={W.min():.3e})")
    if not np.allclose(W, W.T, atol=1e-9):
        violations.append(f"asymmetric (max|W-W.T|={np.abs(W - W.T).max():.3e})")
    if not np.allclose(np.diag(W), 0.0, atol=1e-12):
        violations.append(f"non-zero diag (max|diag|={np.abs(np.diag(W)).max():.3e})")
    assert not violations, (
        "INV-RC-FLOW VIOLATED: weights must be finite, non-negative, "
        f"symmetric, zero-diagonal. Observed violations={violations}, "
        "expected none. Tolerances: |·|<1e-10 negative, |·|<1e-9 asymmetric, "
        f"|·|<1e-12 diag. Context: {context}, N={W.shape[0]}."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(data=st.data())
def test_flow_preserves_finiteness_symmetry_diag(data: st.DataObject) -> None:
    """INV-RC-FLOW: a flow step preserves finite/sym/zero-diag/non-negative."""
    W = data.draw(weight_matrices())
    kappa = data.draw(curvature_dicts(W))
    cfg = RicciFlowConfig(eta=0.05)
    out = discrete_ricci_flow_step(W, kappa, cfg)
    _check_weights_invariants(out, context="random_flow_step")


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(data=st.data())
def test_mass_preserved_when_enabled(data: st.DataObject) -> None:
    """INV-RC-FLOW: total edge mass invariant under preserve_total_edge_mass=True."""
    W = data.draw(weight_matrices())
    # Skip degenerate empty / negligible-mass matrices — the contract only
    # rescales when both totals exceed the float-tolerance gate.
    assume(float(W.sum()) > 1e-6)
    kappa = data.draw(curvature_dicts(W))
    cfg = RicciFlowConfig(eta=0.05, preserve_total_edge_mass=True)
    out = discrete_ricci_flow_step(W, kappa, cfg)

    total_before = float(W.sum())
    total_after = float(out.sum())
    # Tolerance derivation: rescale step is ``new_w * (S_before / S_after)``
    # plus a final ``fill_diagonal(0)``. Diagonal is already zero, so the
    # relative error is dominated by N^2 sum accumulations on N≤12 → ~150
    # additions × eps_64 ≈ 4e-14. Use 1e-9 to absorb extreme magnitudes.
    rel_err = abs(total_before - total_after) / max(total_before, 1e-12)
    assert rel_err < 1e-9, (
        "INV-RC-FLOW VIOLATED: preserve_total_edge_mass=True must keep Σw fixed. "
        f"Observed before={total_before:.6e}, after={total_after:.6e}, "
        f"rel_err={rel_err:.3e}, expected <1e-9. "
        "Tolerance: 1e-9 (≤12² entries × eps_64 ≈ 4e-14, padded for magnitude). "
        f"Context: N={W.shape[0]}, eta=0.05."
    )


@settings(
    deadline=2000,
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    n=st.integers(min_value=4, max_value=8),
    kappa_val=st.floats(min_value=-0.999, max_value=-0.999, allow_nan=False, allow_infinity=False),
)
def test_connectedness_preserved_when_required(n: int, kappa_val: float) -> None:
    """INV-RC-FLOW: bridges are never removed when preserve_connectedness=True.

    A linear chain is the adversarial case — every edge is a bridge, so
    surgery must clamp every singular-tail edge instead of removing it.
    """
    W = _bridge_chain(n, w=1.0)
    # Force singular curvature on every bridge.
    kappa: dict[tuple[int, int], float] = {}
    for i in range(n - 1):
        kappa[(i, i + 1)] = float(kappa_val)
    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=1.0,
        preserve_connectedness=True,
    )

    new_W, events = apply_neckpinch_surgery(W, kappa, cfg)

    actions = [e.action for e in events]
    assert "removed" not in actions, (
        "INV-RC-FLOW VIOLATED: bridges must not be removed when "
        "preserve_connectedness=True. "
        f"Observed actions={actions}, expected no 'removed'. "
        f"Context: linear chain N={n}, every edge is a bridge."
    )
    # All edges should remain at >= eps_weight; mass should still flow through.
    for i in range(n - 1):
        assert new_W[i, i + 1] >= cfg.eps_weight, (
            "INV-RC-FLOW VIOLATED: clamped bridge weight must be >= eps_weight. "
            f"Observed w({i},{i + 1})={new_W[i, i + 1]:.3e}, "
            f"expected >= {cfg.eps_weight}. Context: linear chain N={n}."
        )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(data=st.data())
def test_surgery_records_every_event(data: st.DataObject) -> None:
    """INV-RC-FLOW: every surgery candidate emits exactly one event."""
    W = data.draw(weight_matrices(min_n=4, max_n=8))
    kappa = data.draw(curvature_dicts(W))
    # Inject a few singular-tail curvatures on actually-active edges so the
    # candidate set is non-trivial in most draws.
    n = W.shape[0]
    iu, ju = np.triu_indices(n, k=1)
    active = [(int(i), int(j)) for i, j in zip(iu.tolist(), ju.tolist()) if W[i, j] > 0.0]
    for edge in active[:2]:
        kappa[edge] = -0.999

    cfg = RicciFlowConfig(eta=0.05, max_surgery_fraction=1.0)
    candidates = detect_neckpinch_candidates(W, kappa, cfg)
    _, events = apply_neckpinch_surgery(W, kappa, cfg)

    candidate_set = set(candidates)
    event_edges = {e.edge for e in events}
    assert candidate_set == event_edges, (
        "INV-RC-FLOW VIOLATED: surgery event log must cover every candidate edge. "
        f"Observed candidates={sorted(candidate_set)}, "
        f"events={sorted(event_edges)}, "
        f"missing={sorted(candidate_set - event_edges)}, "
        f"extra={sorted(event_edges - candidate_set)}. "
        "Tolerance: set equality (no slack). "
        f"Context: N={n}, |candidates|={len(candidate_set)}."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    data=st.data(),
    fraction=st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
)
def test_surgery_fraction_bounded(data: st.DataObject, fraction: float) -> None:
    """INV-RC-FLOW: removed-edge count ≤ floor(max_surgery_fraction · n_active)."""
    W = data.draw(weight_matrices(min_n=5, max_n=10))
    kappa = data.draw(curvature_dicts(W))
    n = W.shape[0]
    iu, ju = np.triu_indices(n, k=1)
    active = [(int(i), int(j)) for i, j in zip(iu.tolist(), ju.tolist()) if W[i, j] > 0.0]
    # Push every active edge into the singular tail so the cap is the only
    # thing limiting removals.
    for edge in active:
        kappa[edge] = -0.999

    cfg = RicciFlowConfig(
        eta=0.05,
        eps_neck=1e-3,
        max_surgery_fraction=fraction,
        preserve_connectedness=False,
        allow_disconnect=True,
    )
    _, events = apply_neckpinch_surgery(W, kappa, cfg)
    n_removed = sum(1 for e in events if e.action == "removed")
    cap = int(np.floor(fraction * len(active)))
    assert n_removed <= cap, (
        "INV-RC-FLOW VIOLATED: removed-edge count must be ≤ "
        "floor(max_surgery_fraction × n_active). "
        f"Observed removed={n_removed}, cap={cap}, n_active={len(active)}, "
        f"fraction={fraction:.3f}. Tolerance: integer ≤ (no slack). "
        f"Context: N={n}, all active edges in singular tail."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(W=weight_matrices())
def test_idempotent_with_zero_curvature(W: NDArray[np.float64]) -> None:
    """INV-RC-FLOW: zero curvature is a fixed point under flow + surgery.

    With κ ≡ 0 there is no flow displacement and no singular-tail candidate.
    The only surviving surgery candidates are weights below ``eps_weight``,
    which by Hypothesis draw on ``[0, 1]`` are essentially never produced
    (the strategy emits values either ≥1e-300 or strictly 0). We therefore
    expect the post-step matrix to agree with the input to float precision
    after symmetrisation.
    """
    n = W.shape[0]
    assume(float(W.sum()) > 1e-6)  # excluded the all-zero-mass corner
    kappa = {(i, j): 0.0 for i in range(n) for j in range(i + 1, n) if W[i, j] > 0.0}
    cfg = RicciFlowConfig(eta=0.05, preserve_total_edge_mass=True)

    result = ricci_flow_with_surgery(W, kappa, cfg)
    after = result.weights_after

    # Exclude any tiny weight that fell to/below eps_weight and was clamped
    # by surgery; those are an expected one-shot displacement, not a flow
    # violation.
    surgery_edges = {e.edge for e in result.surgery_events}
    diff = np.abs(after - W)
    if surgery_edges:
        for i, j in surgery_edges:
            diff[i, j] = 0.0
            diff[j, i] = 0.0
    max_diff = float(diff.max()) if diff.size else 0.0

    # Tolerance derivation: explicit-Euler with κ ≡ 0 reduces to
    # ``new_w = max(0, W - 0) = W``; symmetrisation is exact since W is
    # already symmetric; diagonal already zero. Mass-preserving rescale is
    # 1.0 ± O(N²·eps_64) ≈ 1 ± 4e-14. Bound |Δ| < 1e-9.
    assert max_diff < 1e-9, (
        "INV-RC-FLOW VIOLATED: zero curvature must be a fixed point "
        "(modulo eps_weight clamps). "
        f"Observed max|Δ|={max_diff:.3e}, expected <1e-9. "
        "Tolerance: 1e-9 (explicit-Euler + symmetrisation + mass rescale, "
        "≤N²·eps_64 ≈ 4e-14 padded). "
        f"Context: N={n}, |surgery|={len(surgery_edges)}, Σw={float(W.sum()):.3e}."
    )
