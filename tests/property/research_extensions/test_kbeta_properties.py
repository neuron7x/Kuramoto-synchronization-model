# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property tests for INV-KBETA — capital-weighted β Kuramoto coupling.

INV-KBETA: ``K_ij`` is finite, non-negative, symmetric, zero on the diagonal;
``β = 1`` recovers the baseline; uniform multiplicative depth scaling is a
symmetry of the normalised coupling; future-snapshot leakage is rejected.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import (
    CapitalWeightedCouplingConfig,
    L2DepthSnapshot,
    build_capital_weighted_adjacency,
)

from .strategies import l2_depth_snapshots


def _ring_adj(n: int, w: float = 1.0) -> NDArray[np.float64]:
    A = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        j = (i + 1) % n
        A[i, j] = w
        A[j, i] = w
    return A


def _check_kij_invariants(K: NDArray[np.float64], context: str) -> None:
    """INV-KBETA: finite, non-negative, symmetric, zero-diagonal."""
    violations: list[str] = []
    if not np.isfinite(K).all():
        violations.append("non-finite")
    if (K < -1e-10).any():
        violations.append(f"negative (min={K.min():.3e})")
    if not np.allclose(K, K.T, atol=1e-9):
        violations.append(f"asymmetric (max|K-K.T|={np.abs(K - K.T).max():.3e})")
    if not np.allclose(np.diag(K), 0.0, atol=1e-12):
        violations.append(f"non-zero diag (max|diag|={np.abs(np.diag(K)).max():.3e})")
    assert not violations, (
        "INV-KBETA VIOLATED: capital-weighted coupling must be finite, "
        "non-negative, symmetric, zero-diagonal. "
        f"Observed violations={violations}, expected none. "
        f"Tolerances: |·|<1e-10 negative, |·|<1e-9 asymmetric, |·|<1e-12 diag. "
        f"Context: {context}, N={K.shape[0]}."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(snapshot=l2_depth_snapshots())
def test_kbeta_finite_symmetric_zero_diag(snapshot: L2DepthSnapshot) -> None:
    """INV-KBETA: any valid L2 snapshot yields a finite/sym/zero-diag coupling."""
    n = snapshot.bid_sizes.shape[0]
    baseline = _ring_adj(n, w=1.0)
    cfg = CapitalWeightedCouplingConfig(fail_on_future_l2=True)
    # Signal time strictly after snapshot time so the no-look-ahead guard
    # is satisfied by construction.
    signal_ts = snapshot.timestamp_ns + 1

    result = build_capital_weighted_adjacency(baseline, snapshot, signal_ts, cfg)
    _check_kij_invariants(result.coupling, context="kbeta_random_snapshot")
    assert cfg.beta_min <= result.beta <= cfg.beta_max, (
        "INV-KBETA VIOLATED: β must lie in [beta_min, beta_max]. "
        f"Observed β={result.beta:.6f}, expected ∈ [{cfg.beta_min}, {cfg.beta_max}]. "
        f"Tolerance: closed interval (no slack). Context: random snapshot, N={n}."
    )


@settings(deadline=2000, max_examples=50)
@given(
    n=st.integers(min_value=3, max_value=8),
    w=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_beta_one_recovers_baseline(n: int, w: float) -> None:
    """INV-KBETA: β=1 recovers the baseline matrix exactly (no snapshot path)."""
    baseline = _ring_adj(n, w=w)
    cfg = CapitalWeightedCouplingConfig(fail_on_future_l2=True)
    # Use the explicit no-snapshot path which by contract returns β=1 and the
    # baseline unchanged. This tests the contract verbatim across sizes.
    result = build_capital_weighted_adjacency(baseline, None, 0, cfg)
    assert result.beta == 1.0, (
        "INV-KBETA VIOLATED: β must be exactly 1.0 in the no-snapshot fallback. "
        f"Observed β={result.beta!r}, expected 1.0. "
        "Tolerance: float exactness. Context: snapshot=None."
    )
    assert np.allclose(result.coupling, baseline, atol=1e-12), (
        "INV-KBETA VIOLATED: fallback must return baseline unchanged. "
        f"Observed max|Δ|={np.abs(result.coupling - baseline).max():.3e}, "
        f"expected <1e-12. Context: N={n}, ring weight={w}."
    )
    assert result.used_fallback, "no_l2_snapshot path must mark used_fallback=True"


def test_missing_l2_uses_fallback() -> None:
    """INV-KBETA: snapshot=None triggers the fallback with reason='no_l2_snapshot'."""
    baseline = _ring_adj(5, w=1.0)
    cfg = CapitalWeightedCouplingConfig()
    result = build_capital_weighted_adjacency(baseline, None, 0, cfg)
    assert result.used_fallback is True, (
        "INV-KBETA VIOLATED: missing L2 must mark used_fallback=True. "
        f"Observed used_fallback={result.used_fallback}, expected True. "
        "Tolerance: bool exactness. Context: snapshot=None."
    )
    assert result.reason == "no_l2_snapshot", (
        "INV-KBETA VIOLATED: missing L2 must report reason='no_l2_snapshot'. "
        f"Observed reason={result.reason!r}, expected 'no_l2_snapshot'. "
        "Context: snapshot=None."
    )


def test_future_l2_raises() -> None:
    """INV-KBETA: snapshot timestamp strictly after signal_timestamp_ns is rejected."""
    n = 4
    baseline = _ring_adj(n, w=1.0)
    cfg = CapitalWeightedCouplingConfig(fail_on_future_l2=True)
    snapshot = L2DepthSnapshot(
        timestamp_ns=1_000_000_000,
        bid_sizes=np.ones((n, 2), dtype=np.float64),
        ask_sizes=np.ones((n, 2), dtype=np.float64),
        mid_prices=np.full(n, 100.0, dtype=np.float64),
    )
    with pytest.raises(ValueError, match="look-ahead"):
        build_capital_weighted_adjacency(baseline, snapshot, signal_timestamp_ns=0, cfg=cfg)


def test_negative_input_raises() -> None:
    """INV-KBETA: negative bid/ask sizes are fail-closed."""
    n = 3
    baseline = _ring_adj(n)
    cfg = CapitalWeightedCouplingConfig()
    bad = L2DepthSnapshot(
        timestamp_ns=0,
        bid_sizes=-np.ones((n, 2), dtype=np.float64),
        ask_sizes=np.ones((n, 2), dtype=np.float64),
        mid_prices=np.full(n, 100.0, dtype=np.float64),
    )
    with pytest.raises(ValueError, match="non-negative"):
        build_capital_weighted_adjacency(baseline, bad, signal_timestamp_ns=1, cfg=cfg)


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    snapshot=l2_depth_snapshots(),
    scale=st.floats(min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False),
)
def test_uniform_scale_invariance(snapshot: L2DepthSnapshot, scale: float) -> None:
    """INV-KBETA: scaling all depths by c>0 leaves the normalised coupling invariant.

    Mathematical justification: r_i = m_i / median(m) is scale-free, so r_ij
    and the Gini-derived β are invariant under m → c·m. With ``normalize=True``
    the post-multiplication rescale to ``Σ baseline`` further cancels any
    residual drift, so the coupling matrix should agree to float-precision.
    """
    n = snapshot.bid_sizes.shape[0]
    baseline = _ring_adj(n, w=1.0)
    cfg = CapitalWeightedCouplingConfig(fail_on_future_l2=True, normalize=True)
    signal_ts = snapshot.timestamp_ns + 1

    scaled = L2DepthSnapshot(
        timestamp_ns=snapshot.timestamp_ns,
        bid_sizes=snapshot.bid_sizes * scale,
        ask_sizes=snapshot.ask_sizes * scale,
        mid_prices=snapshot.mid_prices,
    )

    base_result = build_capital_weighted_adjacency(baseline, snapshot, signal_ts, cfg)
    scaled_result = build_capital_weighted_adjacency(baseline, scaled, signal_ts, cfg)

    # Tolerance derivation: floor(r) and Gini both involve sum/median ratios on
    # at most 12 entries; relative error is bounded by ~12 * eps_64 ≈ 3e-15.
    # With ``normalize=True`` we rescale by Σ baseline / Σ coupling so the
    # bound becomes additive — use 1e-9 to absorb the renormalisation step.
    diff = float(np.abs(base_result.coupling - scaled_result.coupling).max())
    assert diff < 1e-9, (
        "INV-KBETA VIOLATED: uniform depth scaling must leave normalised "
        "coupling invariant. "
        f"Observed max|Δ|={diff:.3e}, expected <1e-9. "
        "Tolerance: 1e-9 (12-element sum/median + renormalisation, ~12·eps_64). "
        f"Context: N={n}, scale={scale:.3e}, β_orig={base_result.beta:.4f}, "
        f"β_scaled={scaled_result.beta:.4f}."
    )
    # β depends only on Gini(depth_mass) which is scale-free.
    assert abs(base_result.beta - scaled_result.beta) < 1e-9, (
        "INV-KBETA VIOLATED: β must be scale-free (Gini is scale-invariant). "
        f"Observed |Δβ|={abs(base_result.beta - scaled_result.beta):.3e}, "
        "expected <1e-9. Tolerance: 1e-9 (Gini sort + sum, ~N·eps_64). "
        f"Context: N={n}, scale={scale:.3e}."
    )
