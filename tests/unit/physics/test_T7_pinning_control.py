# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T7: pinning control of complex networks.

Invariants under test:
* INV-PIN1 | universal   | returned P satisfies λ_2(L + Γ_P) > ε_pin OR
                          status == INSUFFICIENT (fail-closed).
* INV-PIN2 | conditional | pinning step contractive in linear regime.
* INV-PIN3 | universal   | unpinned subgraph topology preserved.
* INV-PIN4 | universal   | every contract violation → ValueError.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from runtime.pinning_control import (
    PinningReport,
    PinningStatus,
    algebraic_connectivity,
    graph_laplacian,
    pinning_gain_margin,
    pinning_step,
    select_pinning_set,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _path_graph(n: int) -> np.ndarray:
    """Path graph on n nodes (each connected to neighbour)."""
    A = np.zeros((n, n), dtype=np.float64)
    for i in range(n - 1):
        A[i, i + 1] = 1.0
        A[i + 1, i] = 1.0
    return A


def _complete_graph(n: int) -> np.ndarray:
    return np.ones((n, n), dtype=np.float64) - np.eye(n, dtype=np.float64)


# ── Spectral primitives sanity ──────────────────────────────────────────────


def test_graph_laplacian_complete_graph_eigvals_match_textbook() -> None:
    """L(K_N) eigenvalues: 0 (× 1) and N (× N−1)."""
    n = 5
    L = graph_laplacian(_complete_graph(n))
    eigs = sorted(np.linalg.eigvalsh(L))
    assert abs(eigs[0]) < 1e-10
    for ev in eigs[1:]:
        assert abs(ev - n) < 1e-10


def test_algebraic_connectivity_complete_graph_equals_N() -> None:
    """λ_2(L(K_N)) = N."""
    for n in (3, 5, 8):
        lam = algebraic_connectivity(_complete_graph(n))
        assert abs(lam - n) < 1e-10, f"λ_2(K_{n})={lam}, expected {n}"


def test_algebraic_connectivity_path_graph_positive() -> None:
    """Path graph is connected ⇒ λ_2 > 0 (INV-SG2 compat)."""
    for n in (3, 4, 5, 8):
        lam = algebraic_connectivity(_path_graph(n))
        assert lam > 1e-6, f"path P_{n} should be connected, λ_2={lam}"


def test_algebraic_connectivity_disconnected_graph_zero() -> None:
    """Two disconnected components ⇒ λ_2 ≈ 0."""
    A = np.zeros((6, 6), dtype=np.float64)
    A[:3, :3] = _complete_graph(3)
    A[3:, 3:] = _complete_graph(3)
    lam = algebraic_connectivity(A)
    assert abs(lam) < 1e-10, f"disconnected graph λ_2 should be 0, got {lam}"


# ── INV-PIN1: select_pinning_set guarantees gain margin ─────────────────────


def test_INV_PIN1_returns_sufficient_with_enough_gain() -> None:
    """Path graph with strong gain: select_pinning_set finds P with
    λ_2(L + Γ_P) > eps_pin."""
    A = _path_graph(8)
    rep = select_pinning_set(A, gain=2.0, eps_pin=0.5)
    assert isinstance(rep, PinningReport)
    assert rep.status == PinningStatus.SUFFICIENT, (
        f"INV-PIN1: expected SUFFICIENT with strong gain, got {rep.status} "
        f"with gain_margin={rep.gain_margin:.4f}"
    )
    assert rep.gain_margin > 0.5
    # Verify by re-computing gain margin from scratch.
    margin = pinning_gain_margin(A, rep.pinned_indices, gain=2.0)
    assert abs(margin - rep.gain_margin) < 1e-10


def test_INV_PIN1_returns_insufficient_when_gain_too_small() -> None:
    """Tiny gain on a sparse graph: status INSUFFICIENT."""
    A = _path_graph(20)
    rep = select_pinning_set(A, gain=1e-6, eps_pin=0.5, k_max=2)
    assert (
        rep.status == PinningStatus.INSUFFICIENT
    ), f"INV-PIN1: expected INSUFFICIENT with gain=1e-6 + k_max=2, got {rep.status}"
    assert rep.gain_margin <= 0.5


def test_INV_PIN1_pinning_one_node_complete_graph_sufficient() -> None:
    """K_N: pinning ONE node should already give λ_2 ≥ 1."""
    A = _complete_graph(6)
    rep = select_pinning_set(A, gain=1.0, eps_pin=0.5, k_max=1)
    assert rep.status == PinningStatus.SUFFICIENT
    assert len(rep.pinned_indices) == 1
    assert rep.gain_margin > 0.5


# ── INV-PIN2: pinning step is contractive in linear regime ──────────────────


def test_INV_PIN2_pinning_step_contractive_with_zero_target() -> None:
    """One pinning_step with target=0 reduces ||x||² when λ_2(L+Γ_P) > 0
    and dt is below the stability bound."""
    A = _complete_graph(5)
    rep = select_pinning_set(A, gain=1.0, eps_pin=0.1)
    assert rep.status == PinningStatus.SUFFICIENT

    # Stability bound: dt < 2 / λ_max(L + Γ_P).
    L = graph_laplacian(A)
    Gamma = np.zeros_like(L)
    for i in rep.pinned_indices:
        Gamma[i, i] = 1.0
    lam_max = float(np.linalg.eigvalsh(L + Gamma)[-1])
    dt = 0.5 / lam_max  # generous safety margin

    rng = np.random.default_rng(seed=0)
    x = rng.normal(0.0, 1.0, size=5)
    norm_before = float(np.dot(x, x))

    x_next = pinning_step(x, A=A, pinned_indices=rep.pinned_indices, gain=1.0, dt=dt)
    norm_after = float(np.dot(x_next, x_next))
    assert norm_after < norm_before, (
        f"INV-PIN2 VIOLATED: ||x||² did not decrease "
        f"(before={norm_before:.4f}, after={norm_after:.4f})"
    )


def test_INV_PIN2_no_pinning_yields_no_contraction_to_target() -> None:
    """Without pinning, the consensus dynamics drives mean — but doesn't
    necessarily reduce ||x|| toward zero. Proves INV-PIN2 contraction
    is due to pinning, not just the Laplacian flow.
    """
    A = _complete_graph(5)
    L = graph_laplacian(A)
    lam_max = float(np.linalg.eigvalsh(L)[-1])
    dt = 0.5 / lam_max
    rng = np.random.default_rng(seed=1)
    # Construct a state with non-zero mean — Laplacian preserves the mean.
    x = rng.normal(2.0, 1.0, size=5)
    x_next = pinning_step(x, A=A, pinned_indices=(), gain=1.0, dt=dt)
    norm_after = float(np.dot(x_next, x_next))
    # Mean component of size n*2² = 20 is preserved → ||x||² floor ≥ 20.
    assert norm_after > 15.0, (
        f"Negative control: pure Laplacian flow should not reduce ||x|| to zero — "
        f"got {norm_after:.4f}"
    )


# ── INV-PIN3: unpinned subgraph topology preserved ──────────────────────────


def test_INV_PIN3_topology_preserved_outside_pinned_set() -> None:
    """select_pinning_set / pinning_step do not modify A outside P.

    Implementation does not in-place modify A. Verified by snapshot.
    """
    A = _path_graph(8)
    A_snapshot = A.copy()
    rep = select_pinning_set(A, gain=1.0, eps_pin=0.5)
    # Even after select + multiple pinning_steps, A is unchanged.
    rng = np.random.default_rng(seed=3)
    x: np.ndarray = rng.normal(0.0, 1.0, size=8)
    for _ in range(5):
        x = pinning_step(x, A=A, pinned_indices=rep.pinned_indices, gain=1.0, dt=0.05)
    assert np.array_equal(A, A_snapshot), "INV-PIN3 VIOLATED: A modified by pinning operations"


# ── INV-PIN4: fail-closed contracts ─────────────────────────────────────────


def test_INV_PIN4_graph_laplacian_rejects_non_square() -> None:
    A = np.zeros((3, 4), dtype=np.float64)
    with pytest.raises(ValueError, match="square 2-D"):
        graph_laplacian(A)


def test_INV_PIN4_graph_laplacian_rejects_negative_entries() -> None:
    A = np.array([[0.0, -0.1], [-0.1, 0.0]], dtype=np.float64)
    with pytest.raises(ValueError, match="non-negative"):
        graph_laplacian(A)


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"gain": 0.0}, "gain must be > 0"),
        ({"gain": -1.0}, "gain must be > 0"),
        ({"eps_pin": -0.1}, "eps_pin must be ≥ 0"),
        ({"k_max": 0}, "k_max must satisfy"),
        ({"k_max": 100}, "k_max must satisfy"),
    ],
)
def test_INV_PIN4_select_pinning_set_rejects_bad_inputs(kwargs: dict[str, float], msg: str) -> None:
    A = _path_graph(8)
    base: dict[str, Any] = {"A": A, "gain": 1.0, "eps_pin": 0.1}
    base.update(kwargs)
    with pytest.raises(ValueError, match=msg):
        select_pinning_set(**base)


def test_INV_PIN4_pinning_step_rejects_shape_mismatch() -> None:
    A = _path_graph(8)
    x_wrong = np.zeros(5)
    with pytest.raises(ValueError, match="shape mismatch"):
        pinning_step(x_wrong, A=A, pinned_indices=(0,), gain=1.0, dt=0.01)


def test_INV_PIN4_pinning_step_rejects_non_1d_state() -> None:
    A = _path_graph(8)
    x_2d = np.zeros((2, 8))
    with pytest.raises(ValueError, match="x must be 1-D"):
        pinning_step(x_2d, A=A, pinned_indices=(0,), gain=1.0, dt=0.01)


def test_INV_PIN4_pinning_step_rejects_bad_dt() -> None:
    A = _path_graph(8)
    x = np.zeros(8)
    with pytest.raises(ValueError, match="dt must be > 0"):
        pinning_step(x, A=A, pinned_indices=(0,), gain=1.0, dt=0.0)


def test_INV_PIN4_gain_margin_rejects_out_of_range_indices() -> None:
    A = _path_graph(8)
    with pytest.raises(ValueError, match="out-of-range"):
        pinning_gain_margin(A, pinned_indices=(0, 99), gain=1.0)


# ── Determinism ──────────────────────────────────────────────────────────────


def test_INV_HPC1_select_pinning_set_repeatable() -> None:
    """Two calls with identical inputs return identical reports."""
    A = _path_graph(10)
    rep_a = select_pinning_set(A, gain=1.0, eps_pin=0.3)
    rep_b = select_pinning_set(A, gain=1.0, eps_pin=0.3)
    assert rep_a.pinned_indices == rep_b.pinned_indices
    assert rep_a.status == rep_b.status
    assert abs(rep_a.gain_margin - rep_b.gain_margin) < 1e-15


# ── Negative control ────────────────────────────────────────────────────────


def test_negative_control_select_does_not_pin_all_nodes_when_unnecessary() -> None:
    """K_N with strong gain: should pin few (≪ N) nodes to reach ε_pin.

    If the greedy heuristic naively pinned all N nodes regardless of
    margin, the law would be vacuous (you can always force λ_2 ≥ γ
    by pinning everything).
    """
    n = 10
    A = _complete_graph(n)
    rep = select_pinning_set(A, gain=2.0, eps_pin=0.5)
    assert rep.status == PinningStatus.SUFFICIENT
    assert rep.iterations < n, (
        f"Negative control: expected to need < {n} pins on K_{n} with strong gain, "
        f"got {rep.iterations}"
    )
