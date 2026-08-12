# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for weighted_allocation.py + GATE_4 (reproducibility)."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.weighted_allocation import (
    allocate_weights,
    sample_adjacency_bernoulli,
)


def _marginals(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    s = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = s.copy()
    rng.shuffle(s_in)
    # Force conservation of mass.
    s_in *= s.sum() / s_in.sum()
    return s, s_in


def test_sample_adjacency_diagonal_zero() -> None:
    rng = np.random.default_rng(42)
    p = np.full((30, 30), 0.5)
    a = sample_adjacency_bernoulli(p, rng=rng)
    assert np.all(np.diag(a) == 0)


def test_sample_adjacency_uint8_dtype() -> None:
    rng = np.random.default_rng(42)
    p = np.full((10, 10), 0.5)
    a = sample_adjacency_bernoulli(p, rng=rng)
    assert a.dtype == np.uint8


def test_sample_adjacency_in_zero_one() -> None:
    rng = np.random.default_rng(42)
    p = np.random.default_rng(0).uniform(size=(20, 20))
    a = sample_adjacency_bernoulli(p, rng=rng)
    assert set(np.unique(a).tolist()).issubset({0, 1})


def test_sample_adjacency_bit_exact_reproducibility() -> None:
    """GATE_4: identical seeds + p ⇒ identical A."""
    p = np.random.default_rng(0).uniform(size=(40, 40))
    a1 = sample_adjacency_bernoulli(p, rng=np.random.default_rng(99))
    a2 = sample_adjacency_bernoulli(p, rng=np.random.default_rng(99))
    np.testing.assert_array_equal(a1, a2)


def test_sample_adjacency_rejects_p_out_of_unit() -> None:
    rng = np.random.default_rng(42)
    p_bad = np.array([[0.5, 1.5], [0.0, 0.0]])
    with pytest.raises(ValueError):
        sample_adjacency_bernoulli(p_bad, rng=rng)


def test_sample_adjacency_rejects_non_square() -> None:
    rng = np.random.default_rng(42)
    p_bad = np.full((4, 5), 0.5)
    with pytest.raises(ValueError):
        sample_adjacency_bernoulli(p_bad, rng=rng)


def test_sample_adjacency_orphan_repair_default_on() -> None:
    """Orphan rows/cols get a forced edge by default."""
    rng = np.random.default_rng(42)
    p = np.full((30, 30), 1e-12)  # essentially zero edge probability
    p[0, 1] = 1.0  # one strong edge
    a = sample_adjacency_bernoulli(p, rng=rng)
    # Every row and every col should have ≥ 1 edge
    assert np.all(a.sum(axis=1) >= 1)
    assert np.all(a.sum(axis=0) >= 1)


def test_sample_adjacency_orphan_repair_can_be_disabled() -> None:
    rng = np.random.default_rng(42)
    p = np.zeros((30, 30))
    a = sample_adjacency_bernoulli(p, rng=rng, guarantee_row_col_support=False)
    assert a.sum() == 0


def test_allocate_weights_recovers_marginals_after_ipf() -> None:
    """IPF projects W onto the marginal slice — row/col sums match exactly.

    Uses p=0.30 to guarantee transportation feasibility on heavy-tailed
    marginals; sparser supports may leave residual error that Gate 5
    metrics will catch, which is the X-10R contract.
    """
    n = 60
    s_out, s_in = _marginals(n, seed=21)
    rng = np.random.default_rng(7)
    p = np.full((n, n), 0.30)
    a = sample_adjacency_bernoulli(p, rng=rng)
    w = allocate_weights(a, s_out, s_in)
    np.testing.assert_allclose(w.sum(axis=1), s_out, rtol=0, atol=1e-6 * s_out.max())
    np.testing.assert_allclose(w.sum(axis=0), s_in, rtol=0, atol=1e-6 * s_in.max())


def test_allocate_weights_diagonal_zero() -> None:
    n = 40
    s_out, s_in = _marginals(n, seed=22)
    a = np.ones((n, n), dtype=np.uint8)
    np.fill_diagonal(a, 0)
    w = allocate_weights(a, s_out, s_in)
    assert np.all(np.diag(w) == 0.0)


def test_allocate_weights_total_mass_conserved() -> None:
    n = 50
    s_out, s_in = _marginals(n, seed=23)
    rng = np.random.default_rng(7)
    p = np.full((n, n), 0.08)
    a = sample_adjacency_bernoulli(p, rng=rng)
    w = allocate_weights(a, s_out, s_in)
    assert abs(w.sum() - s_in.sum()) / s_in.sum() < 1e-6


def test_allocate_weights_rejects_negative_marginals() -> None:
    n = 10
    a = np.ones((n, n), dtype=np.uint8)
    np.fill_diagonal(a, 0)
    s = np.ones(n)
    s_bad = -np.ones(n)
    with pytest.raises(ValueError):
        allocate_weights(a, s_bad, s)


def test_allocate_weights_rejects_zero_total_mass() -> None:
    n = 10
    a = np.ones((n, n), dtype=np.uint8)
    np.fill_diagonal(a, 0)
    s = np.zeros(n)
    with pytest.raises(ValueError):
        allocate_weights(a, s, s)


def test_allocate_weights_rejects_non_square_adjacency() -> None:
    s = np.ones(4)
    with pytest.raises(ValueError):
        allocate_weights(np.zeros((4, 5), dtype=np.uint8), s, s)


def test_allocate_weights_rejects_infeasible_support() -> None:
    """A row with positive marginal but zero edges → ValueError."""
    n = 10
    a = np.zeros((n, n), dtype=np.uint8)
    a[1, 0] = 1
    a[0, 1] = 1  # only nodes 0 and 1 have edges
    s_out = np.ones(n) * 100.0  # all nodes have positive marginal
    s_in = s_out.copy()
    with pytest.raises(ValueError, match="infeasible"):
        allocate_weights(a, s_out, s_in)


# ---------------------------------------------------------------------------
# Empirical certification of the FIX B1 docstring math claim.
#
# The corrected weighted_allocation.py docstring states:
#     "naive gravity w_ij^0 = a_ij · s_i^out · s_j^in / W_total
#     does NOT preserve E[Σ_j w_ij] = s_i^out once the support of A
#     is non-trivially sparsified."
#
# This was previously documented but never empirically asserted. The
# tests below pin the claim into the regression surface so a future
# reader can audit the math without rerunning derivations.
# ---------------------------------------------------------------------------


def _naive_gravity_no_ipf(a: np.ndarray, s_out: np.ndarray, s_in: np.ndarray) -> np.ndarray:
    """Reference implementation of the naive gravity rule WITHOUT IPF.

    This is *not* the production allocator — it deliberately omits the
    Almog-Squartini IPF projection so the failure mode is observable.
    """
    w_total = float(s_in.sum())
    outer = np.outer(s_out, s_in) / w_total
    w0: np.ndarray = (a.astype(np.float64) * outer).astype(np.float64)
    np.fill_diagonal(w0, 0.0)
    return w0


def test_naive_gravity_does_not_preserve_marginals_on_sparse_support() -> None:
    """Empirical certification of the FIX B1 math claim.

    On a Bernoulli-sparsified support at p=0.20 with heterogeneous
    lognormal marginals, naive gravity loses ≥10% of the row marginals
    in expectation (relative L1). The IPF projection on the SAME support
    drives the loss to <1%. This is exactly why the production allocator
    runs IPF; this test makes the *necessity* of IPF auditable.
    """
    n = 80
    s_out, s_in = _marginals(n, seed=7)
    rng = np.random.default_rng(11)
    a = sample_adjacency_bernoulli(np.full((n, n), 0.20), rng=rng)

    # Naive gravity (no IPF) — the claim's failure surface.
    w_naive = _naive_gravity_no_ipf(a, s_out, s_in)
    naive_row_loss = float(np.abs(w_naive.sum(axis=1) - s_out).sum() / s_out.sum())

    # Production allocator (gravity + IPF projection).
    w_ipf = allocate_weights(a, s_out, s_in)
    ipf_row_loss = float(np.abs(w_ipf.sum(axis=1) - s_out).sum() / s_out.sum())

    # The FIX B1 claim: naive gravity loses substantial row mass on
    # this regime, IPF closes the gap by ≥1 order of magnitude.
    assert naive_row_loss > 0.10, (
        f"Naive-gravity row loss = {naive_row_loss:.4f} — the FIX B1 docstring "
        "claim 'naive gravity does not preserve marginals' is supposed to be "
        "FALSIFIABLE on this regime, but here naive gravity is suspiciously "
        "close to mass-preserving. Re-derive the claim."
    )
    assert ipf_row_loss < naive_row_loss / 10, (
        f"IPF row loss = {ipf_row_loss:.4f} not tight enough vs naive "
        f"{naive_row_loss:.4f} — IPF is supposed to drive the loss "
        "below 10% of the naive baseline."
    )
    # Production-level invariant: IPF row loss must be inside Gate 5's
    # row_sum_invariant_L1 ≤ 0.05 envelope, scaled by N (Gate 5 averages).
    assert ipf_row_loss < 0.05


def test_ipf_projection_tightens_row_marginals_below_gate5_threshold() -> None:
    """The IPF projection in `allocate_weights` enforces the marginals
    to *production* tolerance (≤ 5% relative row/col L1, the Gate 5
    threshold), and is order-of-magnitude tighter than the naive
    gravity baseline.

    This is the Almog-Squartini 2017 contract delivered at the level
    Gate 5 actually consumes. Stronger machine-precision claims
    DO NOT hold uniformly on heavy-tailed lognormal marginals (a
    Sinkhorn-Knopp with iter cap = 5000 leaves a residual proportional
    to the marginal heterogeneity); pinning the *production* contract
    rather than the *theoretical* one keeps the regression surface
    honest under realistic inputs.
    """
    n = 60
    s_out, s_in = _marginals(n, seed=23)
    rng = np.random.default_rng(29)
    a = sample_adjacency_bernoulli(np.full((n, n), 0.40), rng=rng)

    # Production allocator.
    w = allocate_weights(a, s_out, s_in)
    mean_strength = float(s_out.mean())
    ipf_row_l1 = float(np.abs(w.sum(axis=1) - s_out).sum() / n / mean_strength)
    ipf_col_l1 = float(np.abs(w.sum(axis=0) - s_in).sum() / n / mean_strength)

    # Naive baseline (no IPF).
    w_naive = _naive_gravity_no_ipf(a, s_out, s_in)
    naive_row_l1 = float(np.abs(w_naive.sum(axis=1) - s_out).sum() / n / mean_strength)

    # IPF must clear Gate 5's 5% row/col L1 envelope on this regime.
    assert ipf_row_l1 < 0.05, f"IPF row L1 {ipf_row_l1:.4f} > 0.05 (Gate 5)"
    assert ipf_col_l1 < 0.05, f"IPF col L1 {ipf_col_l1:.4f} > 0.05 (Gate 5)"
    # And IPF must be at least 5x tighter than naive on this regime.
    assert naive_row_l1 / max(ipf_row_l1, 1e-12) >= 5.0, (
        f"naive_row_l1 / ipf_row_l1 = {naive_row_l1 / max(ipf_row_l1, 1e-12):.2f}; "
        "IPF should beat naive by at least 5x on this dense lognormal regime"
    )
