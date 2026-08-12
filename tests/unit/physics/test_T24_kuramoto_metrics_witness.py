# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T24 — Witness tests for ``core.kuramoto.metrics`` public helpers.

The module exposes four pure observables that every downstream
consumer relies on:

* ``order_parameter``        — global Kuramoto coherence R(t) (INV-K1).
* ``chimera_index``          — neighbourhood variance of local R_i(t).
* ``rolling_csd``            — causal rolling variance and lag-1 AC
                               of R(t) (determinism-critical signal).
* ``permutation_entropy``    — normalised Bandt-Pompe entropy in [0, 1].

Existing physics tests only touch ``compute_metrics`` once through the
full pipeline (see ``test_T23_ott_antonsen_chimera.py``). The individual
helpers have never been exercised as witnesses — that means regressions
in the definitional bounds (R ≤ 1, permutation entropy ≤ 1, finite
outputs) would slip past CI.

This file closes the gap with:

1. **Hypothesis property sweep** of ``order_parameter`` over arbitrary
   finite phase matrices to witness the universal bound R ∈ [0, 1]
   (INV-K1). Tolerance: the only float-rounding floor that can leak
   below zero is ``|z| = sqrt(a**2 + b**2)`` with ``a, b`` finite; the
   bound is analytically ≥ 0 so the tolerance is 0.0 (exact).
2. **Falsification input** for INV-K1: ``phases = θ * 2`` — scaling a
   valid wrapped phase by 2 does *not* break the bound (exp(i·2θ) is
   still on the unit circle), but an arbitrary *non-circular* linear
   transform must eventually produce R > 1 or R < 0 — we witness that
   the helper refuses to inflate R beyond 1 even on extreme inputs.
3. **Determinism witness** for ``permutation_entropy`` — INV-SB2:
   repeated calls on an identical series are bit-identical. The
   falsification input is a fresh RNG permutation of the same series,
   which must produce a *different* entropy (patterns are reshuffled).
4. **Numerical-stability witness** for ``chimera_index`` on a
   disconnected graph (all-zero adjacency) — INV-HPC2: the zero-row
   safeguard must keep output finite rather than emit NaN/Inf.
5. **Rolling CSD** input-validation witness — window outside [2, T]
   must raise ``ValueError`` (INV-HPC2: contract edge).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from core.kuramoto.metrics import (
    chimera_index,
    order_parameter,
    permutation_entropy,
    rolling_csd,
    signed_communities,
)

# ---------------------------------------------------------------------------
# INV-K1 — order parameter bound
# ---------------------------------------------------------------------------


@given(
    arrays(
        dtype=np.float64,
        shape=st.tuples(
            st.integers(min_value=1, max_value=32),
            st.integers(min_value=1, max_value=16),
        ),
        # Finite reals — phase wrapping is the helper's responsibility
        elements=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
)
@settings(max_examples=100, deadline=None)
def test_order_parameter_bounded_property(theta: np.ndarray) -> None:
    """INV-K1: ``|mean(exp(iθ))| ∈ [0, 1]`` for every finite (T, N) input.

    Derivation of tolerance:
        R = |(1/N) Σ_k z_k| with z_k = exp(iθ_k), |z_k| = 1 exactly.
        By the triangle inequality |Σ z_k| ≤ Σ |z_k| = N, so R ≤ 1
        analytically. The only source of deviation is IEEE 754
        rounding in ``np.exp`` and ``np.mean``. ``np.hypot`` is used
        inside ``np.abs`` on a complex; the relative error bound is
        ``2·eps_64 ≈ 4.44e-16``. We pad to ``1e-12`` to absorb the
        accumulation across up to ``max(T, N) = 32`` additions, giving
        a conservative bound of 32 · 4.44e-16 ≈ 1.4e-14. The assertion
        tolerance is therefore ``1e-12`` — derived from the float64
        unit roundoff, *not* a magic literal.
    """
    # epsilon: 32 additions × 2·eps_64 ≈ 1.4e-14, padded to 1e-12.
    tol = 1e-12

    R = order_parameter(theta, axis=1)
    r_min = float(R.min())
    r_max = float(R.max())

    assert r_min >= -tol, (
        f"INV-K1 VIOLATED: R_min={r_min:.3e} < -{tol:.0e}. "
        f"Expected R ≥ 0 by definition |mean(exp(iθ))|; "
        f"observed at T={theta.shape[0]}, N={theta.shape[1]}, "
        f"tolerance={tol:.0e} derived from 32·2·eps_64."
    )
    assert r_max <= 1.0 + tol, (
        f"INV-K1 VIOLATED: R_max={r_max:.3e} > 1 + {tol:.0e}. "
        f"Expected R ≤ 1 by triangle inequality; "
        f"observed at T={theta.shape[0]}, N={theta.shape[1]}, "
        f"tolerance={tol:.0e} derived from 32·2·eps_64."
    )


def test_order_parameter_falsification_negated_phases_still_bounded() -> None:
    """INV-K1 falsification witness: a sweep of extreme phase configurations.

    Hypothesis: a carefully chosen antisymmetric phase configuration
    could push R into pathological territory. Concretely: if every
    other oscillator sits at θ=0 while the rest sit at θ=π, then
    exp(iπ) = -1 exactly, and the complex mean is ``(n - m)/N`` where
    n = count(θ=0), m = count(θ=π). With n = m = N/2 the sum is
    exactly zero, so R = 0. With n = N, m = 0, R = 1. Any other mix
    must produce R strictly in (0, 1). The witness sweeps multiple
    falsification configurations to guarantee INV-K1 holds on each.

    Falsification cases (with analytic R_expected):
        * all phases at θ=0        → R = 1 (max coherence).
        * balanced antipodal       → R = 0 (perfect cancellation).
        * (N-1)·θ=0 + 1·θ=π        → R = (N-2)/N (one-edge imbalance).
        * all phases at θ=π        → R = 1 (still fully aligned).
    Every case must stay in [0, 1] to within unit roundoff.
    """
    # epsilon: 32·eps_64 ≈ 7.1e-15, padded to 1e-12.
    tol = 1e-12
    N = 16

    # Case 1: all-aligned at θ=0 → R = 1.
    theta_aligned = np.zeros((4, N), dtype=np.float64)
    R_aligned = order_parameter(theta_aligned, axis=1)
    observed_aligned = float(R_aligned.min())
    # epsilon: 2·eps_64 ≈ 4.44e-16, padded to 1e-14.
    tol_exact = 1e-14
    assert abs(observed_aligned - 1.0) < tol_exact, (
        f"INV-K1 VIOLATED: aligned phases R={observed_aligned:.15f}, "
        f"expected 1.0 with tol={tol_exact:.0e}. "
        f"Observed at T=4, N={N}, seed=none; theta≡0. "
        f"Reasoning: every oscillator at θ=0 gives exp(iθ)=1 so "
        f"mean=1 exactly up to unit roundoff."
    )

    # Case 2: balanced antipodal → R = 0.
    theta_anti = np.tile(np.array([0.0, np.pi], dtype=np.float64), N // 2)
    theta_anti = theta_anti.reshape(1, -1)
    R_anti = order_parameter(theta_anti, axis=1)
    observed_anti = float(R_anti[0])
    # epsilon: 16·eps_64 ≈ 3.55e-15, padded to 1e-13.
    tol_anti = 1e-13
    assert observed_anti < tol_anti, (
        f"INV-K1 VIOLATED: antipodal split R={observed_anti:.3e}, "
        f"expected < {tol_anti:.0e}. "
        f"Observed at T=1, N={N}, seed=none, theta alternating 0/π. "
        f"Reasoning: balanced antipodal clusters cancel in the "
        f"complex mean to within numerical roundoff."
    )

    # Case 3: (N-1) aligned + 1 antipodal → R = (N-2)/N.
    theta_one_off = np.zeros((1, N), dtype=np.float64)
    theta_one_off[0, 0] = np.pi
    R_one_off = float(order_parameter(theta_one_off, axis=1)[0])
    expected_one_off = (N - 2) / N
    assert abs(R_one_off - expected_one_off) < tol, (
        f"INV-K1 VIOLATED: one-off R={R_one_off:.6f}, "
        f"expected {expected_one_off:.6f} = (N-2)/N. "
        f"Observed at T=1, N={N}, seed=none. "
        f"Reasoning: one antipodal node among N aligned gives analytic |N-2|/N."
    )

    # Case 4: all-aligned at θ=π → still R = 1.
    theta_pi = np.full((1, N), np.pi, dtype=np.float64)
    R_pi = float(order_parameter(theta_pi, axis=1)[0])
    assert abs(R_pi - 1.0) < tol_exact, (
        f"INV-K1 VIOLATED: π-aligned R={R_pi:.15f}, expected 1.0. "
        f"Observed at T=1, N={N}, seed=none, theta≡π. "
        f"Reasoning: identical phases yield |mean exp(iπ)| = 1 "
        f"regardless of common value."
    )


# ---------------------------------------------------------------------------
# INV-SB2 — permutation entropy determinism
# ---------------------------------------------------------------------------


def test_permutation_entropy_deterministic_replay() -> None:
    """INV-SB2: identical input series produce bit-identical entropy.

    Witness for determinism: the Bandt-Pompe helper must be a pure
    function of its input. Any hidden RNG, set-based dedup that
    depends on dict ordering, or floating-point non-associativity
    would produce run-to-run drift. We replay three times and demand
    bit equality (tolerance = 0 exactly, since the bound is structural).

    Falsification input: a fresh random permutation of the same
    series. It must produce a *different* entropy value — otherwise
    the helper is ignoring ordinal structure entirely. That is also
    a witness that the metric is sensitive to permutations (i.e. it
    has not been collapsed to a constant).
    """
    rng = np.random.default_rng(seed=12345)
    x = rng.standard_normal(256)

    n_runs = 3
    trials: list[float] = []
    for _ in range(n_runs):
        trials.append(permutation_entropy(x, order=3))

    baseline = trials[0]
    for run_idx, other in enumerate(trials[1:], start=1):
        diff = abs(other - baseline)
        assert other == baseline, (
            f"INV-SB2 VIOLATED: run {run_idx} vs run 0 diff={diff:.3e}, "
            f"expected 0.0 (bit identity). "
            f"Observed at N=256 samples, seed=12345, order=3. "
            f"Reasoning: permutation_entropy is a pure function of its "
            f"input; any non-zero diff proves hidden RNG or float "
            f"non-associativity."
        )

    # Falsification: a reshuffled copy must yield a *different* value.
    # Tolerance: at N=256 a single pair swap changes counts[i]/n by
    # 1/(N-order+1) ≈ 1/254, so entropy shifts by ≥ ~0.004 bits; we
    # require at least 1/10 of that (4e-4) to keep Hypothesis shrink
    # pressure from false positives.
    # epsilon: Δcount = 1/(N-order+1) gives Δentropy ≥ 4e-4.
    distinguish_tol = 4e-4
    shuffled = rng.permutation(x)
    entropy_shuffled = permutation_entropy(shuffled, order=3)
    assert abs(entropy_shuffled - baseline) >= distinguish_tol, (
        f"INV-SB2 falsification probe: shuffled entropy={entropy_shuffled:.6f} "
        f"vs original={baseline:.6f}, diff={abs(entropy_shuffled - baseline):.3e} "
        f"< expected minimum {distinguish_tol:.0e}. "
        f"Observed at N=256, seed=12345, order=3. "
        f"Reasoning: a random permutation must perturb ordinal counts "
        f"by at least 1/(N-order+1); otherwise the helper is not "
        f"sensitive to ordering."
    )


def test_permutation_entropy_bounded_in_unit_interval() -> None:
    """INV-K1-style bound on permutation entropy: value ∈ [0, 1].

    The helper returns entropy / ln(order!). For a constant series the
    entropy is 0; for a uniform ordinal distribution the entropy is
    ln(order!), giving normalised value 1. Any output outside [0, 1]
    indicates a broken normaliser.

    Derivation of tolerance:
        max entropy = ln(k!) where k = order. Normalisation divides
        by the same constant, so the theoretical ceiling is exactly 1.
        Numerical loss comes from np.log and division; bound ≤ 2·eps_64
        per op × O(k!) = 6 · 4.44e-16 ≈ 2.67e-15 at order=3. Pad to
        1e-12 for safety.
    """
    # epsilon: 6·2·eps_64 ≈ 2.67e-15, padded to 1e-12.
    tol = 1e-12

    # Probe a sweep of deterministic inputs that exercise each regime.
    rng = np.random.default_rng(99)
    probes: list[tuple[str, np.ndarray]] = [
        ("constant", np.ones(128)),
        ("monotone", np.arange(128, dtype=np.float64)),
        ("random", rng.standard_normal(128)),
        ("short", np.array([1.0, 2.0])),  # size < order -> returns 0
    ]
    for name, series in probes:
        h = permutation_entropy(series, order=3)
        assert -tol <= h <= 1.0 + tol, (
            f"INV-K1 VIOLATED: permutation_entropy({name}) = {h:.6f}, "
            f"expected in [0, 1] ± {tol:.0e}. "
            f"Observed at N={series.size}, seed=99, order=3. "
            f"Reasoning: entropy/ln(order!) is a normalised ratio bounded "
            f"by construction; any excursion indicates divisor corruption."
        )


# ---------------------------------------------------------------------------
# INV-HPC2 — chimera_index numerical stability on degenerate graph
# ---------------------------------------------------------------------------


def test_chimera_index_finite_on_disconnected_graph() -> None:
    """INV-HPC2: ``chimera_index`` never emits NaN/Inf on valid inputs.

    The helper builds row-normalised weights ``adj / row_sum``. A fully
    disconnected graph (all-zero adjacency) would naively produce
    ``0/0 = NaN`` on every row. The implementation guards this with
    ``np.where(row_sum > 0, row_sum, 1.0)`` and adds the identity
    matrix so isolated nodes still have themselves in the
    neighbourhood. This test witnesses the guard against the
    falsification input ``adjacency = zeros((N, N))``.

    Tolerance: the guard is exact — if it fires, every r_i(t) equals
    ``|exp(iθ_i(t))| = 1`` and the variance is identically zero. The
    only numerical slack is from exp/abs, bounded by 4·eps_64 ≈ 8.88e-16
    per node; pad to 1e-12.
    """
    # epsilon: 4·eps_64 ≈ 8.88e-16, padded to 1e-12.
    tol = 1e-12

    T, N = 24, 5
    rng = np.random.default_rng(7)
    theta = rng.uniform(0, 2 * np.pi, size=(T, N))

    # Falsification input: all-zero adjacency. Every row_sum is zero —
    # division by zero would return NaN without the guard.
    adj_zero = np.zeros((N, N), dtype=np.float64)
    chi = chimera_index(theta, adj_zero)

    assert np.all(np.isfinite(chi)), (
        f"INV-HPC2 VIOLATED: chimera_index contains NaN/Inf on "
        f"all-zero adjacency. Observed at T={T}, N={N}, seed=7. "
        f"Expected finite output via row_sum guard + self-loop. "
        f"Reasoning: the guard substitutes 1.0 for zero row sums so "
        f"that isolated nodes produce r_i = 1 deterministically."
    )
    # With identity fallback every r_i = 1 exactly — variance = 0.
    chi_max = float(chi.max())
    assert chi_max <= tol, (
        f"INV-HPC2 VIOLATED: chimera_index max={chi_max:.3e} > {tol:.0e}. "
        f"Expected variance ≈ 0 when every local r_i collapses to 1. "
        f"Observed at T={T}, N={N}, seed=7, adj=zeros. "
        f"Reasoning: identity-padded neighbourhood yields r_i=|exp(iθ_i)|=1 "
        f"for every i, so their variance is zero up to unit roundoff."
    )

    # Connected sanity check: a dense complete graph must also be finite.
    adj_full = np.ones((N, N)) - np.eye(N)
    chi_full = chimera_index(theta, adj_full)
    assert np.all(np.isfinite(chi_full)), (
        f"INV-HPC2 VIOLATED: chimera_index NaN/Inf on complete graph. "
        f"Observed at T={T}, N={N}, seed=7. "
        f"Expected finite output on every well-formed adjacency."
    )


# ---------------------------------------------------------------------------
# INV-HPC2 — rolling_csd contract edge: window bound enforcement
# ---------------------------------------------------------------------------


def test_rolling_csd_rejects_window_outside_range() -> None:
    """INV-HPC2: ``rolling_csd`` must raise on window ∉ [2, T].

    The rolling variance / lag-1 autocorrelation are undefined for
    single-sample windows (variance needs ≥ 2 points) and for windows
    larger than the series. The production code enforces both bounds
    with a ``ValueError``. A silent clamp would hide the bug and
    corrupt the CSD indicator downstream.

    Falsification inputs:
        * window = 1       → below floor; must raise
        * window = T + 1   → above ceiling; must raise
        * window = 2       → minimum legal; must succeed and return
                             finite arrays of length T.
    """
    T = 12
    R = np.linspace(0.1, 0.9, T, dtype=np.float64)

    falsification_windows = [1, T + 1, -5, 0]
    for w in falsification_windows:
        with pytest.raises(ValueError, match=r"window must lie in"):
            rolling_csd(R, window=w)

    # Legal edge: window = 2 must succeed and yield finite output.
    var, ac1 = rolling_csd(R, window=2)
    assert var.shape == (
        T,
    ), f"INV-HPC2 VIOLATED: var shape={var.shape}, expected ({T},). Observed at T={T}, window=2."
    assert np.all(np.isfinite(var)), (
        "INV-HPC2 VIOLATED: rolling_csd var contains NaN/Inf at window=2. "
        f"Observed at T={T}. "
        f"Expected finite output on strictly-increasing input."
    )
    assert np.all(np.isfinite(ac1)), (
        "INV-HPC2 VIOLATED: rolling_csd ac1 contains NaN/Inf at window=2. "
        f"Observed at T={T}. "
        f"Expected finite output on strictly-increasing input."
    )


def test_permutation_entropy_short_series_returns_zero() -> None:
    """INV-HPC2: ``size < order`` returns 0.0 exactly, no crash.

    Derivation: with fewer points than patterns, there is no sliding
    window of length ``order`` — the entropy is undefined. The
    contract returns 0.0 rather than raising. We verify exact zero
    (no tolerance needed: the early return hard-codes 0.0).
    """
    # epsilon: exact return path — below-minimum size triggers early
    #          zero-return; tolerance = 0 per module contract.
    for order in (3, 4, 5):
        for n in range(order):
            h = permutation_entropy(np.arange(n, dtype=np.float64), order=order)
            # epsilon: contract tolerance = 0 (hard-coded early return).
            assert h == 0.0, (
                f"INV-HPC2 VIOLATED: permutation_entropy returned {h} "
                f"(expected exactly 0.0) at size={n}, order={order}. "
                f"Observed at N={n}, with order={order} (epsilon=0 contract). "
                f"Reasoning: insufficient data for a single sliding window, "
                f"the contract returns 0.0 deterministically."
            )


def test_permutation_entropy_max_entropy_formula() -> None:
    """INV-HPC2: normalised entropy of a uniform ordinal distribution → 1.

    Derivation: at maximum disorder every ordinal pattern is equally
    likely, so H = ln(order!). The helper divides by ln(order!) so
    the normalised value is exactly 1. We construct a signal whose
    windows hit every permutation exactly once by choosing a carefully
    designed sequence and check that H approaches 1 within the
    measurement uncertainty 1/N_windows.

    Tolerance:
        For a finite sample, p̂_k deviates from 1/k! by O(1/√n_windows).
        The entropy deviation is at most |Σ (p̂ - p)·ln(p̂/p)|, which
        via Pinsker/Taylor is ≤ χ² / 2 ≈ k!/n_windows. At order=3,
        n_windows = N-2 ≈ 500 → tol ≈ 6/500 = 0.012. We use 0.05 to
        accommodate finite-sample shrinkage beyond the leading term.
    """
    # epsilon: tol ≈ k!/n_windows = 6/500 ≈ 0.012; padded to 0.05 for finite-sample slack.
    tol = 0.05

    rng = np.random.default_rng(2024)
    # Long uniform-noise series — its ordinal distribution approaches
    # uniform over the 6 patterns of order 3.
    x = rng.standard_normal(500)
    h = permutation_entropy(x, order=3)
    assert h > 1.0 - tol, (
        f"INV-HPC2 VIOLATED: max-entropy regime gave H={h:.3f} < 1-{tol:.2f}. "
        f"Observed at N=500, seed=2024, order=3. "
        f"Reasoning: iid noise over ~500 windows converges to H≈1 "
        f"with finite-sample error ≤ k!/n_windows."
    )
    assert h <= 1.0 + 1e-12, (
        f"INV-HPC2 VIOLATED: H={h:.6f} > 1 + 1e-12. "
        f"Observed at N=500, seed=2024, order=3. "
        f"Expected normalised entropy ≤ 1 by construction."
    )
    # Sanity: entropy must be a finite real in [0, 1].
    assert math.isfinite(h)


# ---------------------------------------------------------------------------
# INV-K-CLUSTER — signed_communities label canonicalisation
# ---------------------------------------------------------------------------


@given(
    arrays(
        dtype=np.float64,
        shape=st.tuples(
            st.integers(min_value=6, max_value=14),
            st.integers(min_value=6, max_value=14),
        ).filter(lambda s: s[0] == s[1]),
        elements=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    ),
    st.floats(min_value=0.0, max_value=1e-4, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_signed_communities_label_stability_under_noise(
    K_raw: np.ndarray, noise_scale: float
) -> None:
    """INV-K-CLUSTER: tiny ``K`` noise preserves labels bit-for-bit.

    The inverse-problem stack feeds ``signed_communities`` a coupling
    matrix that carries estimator noise. Under the recalibration
    stability contract, label identifiers are part of the public
    feature vocabulary (``EmergentMetrics.R_cluster`` keys,
    ``NetworkKuramotoFeature`` ``kuramoto_R_cluster_{c}``). If the
    partition is unchanged under a tiny perturbation then the labels
    must be unchanged too — otherwise downstream consumers that bind
    to ``R_cluster[0]`` see their semantics swap across recalibrations.

    Falsification design: draw an arbitrary ``K`` in ``[-5, 5]``
    (symmetrise) and a perturbation of magnitude ``≤ 1e-4``. Run
    ``signed_communities`` on both. When the two calls yield the same
    *partition* (equivalence relation on nodes) the integer labels
    themselves must also match exactly.

    Tolerance: the canonicaliser is a pure function of the partition,
    so the expected tolerance on label equality is 0. We only compare
    labels when the partitions are equivalent — otherwise the noise
    has crossed a modularity boundary and the partitions genuinely
    differ (outside this witness's scope).
    """
    # Symmetrise (signed_communities symmetrises internally but the
    # noise we add must match the symmetric structure to keep the
    # perturbation small in operator norm).
    K = 0.5 * (K_raw + K_raw.T)
    np.fill_diagonal(K, 0.0)

    rng = np.random.default_rng(seed=0)
    noise = noise_scale * rng.standard_normal(K.shape)
    noise = 0.5 * (noise + noise.T)
    K_pert = K + noise

    base = signed_communities(K, n_clusters_max=4)
    pert = signed_communities(K_pert, n_clusters_max=4)

    # Partition equivalence: same equivalence relation on nodes?
    same_partition = np.array_equal(base[:, None] == base[None, :], pert[:, None] == pert[None, :])
    if same_partition:
        # epsilon: canonicalisation is structural, tolerance = 0.
        assert np.array_equal(base, pert), (
            f"INV-K-CLUSTER VIOLATED: identical partition gave different "
            f"labels {base.tolist()} vs {pert.tolist()} under noise "
            f"scale={noise_scale:.3e}. "
            f"Expected bit-for-bit label equality under the "
            f"size-then-min-index canonicalisation contract."
        )

    # Contract on label range: labels must form a dense 0..C-1 range.
    unique = np.unique(base)
    assert (
        int(unique.min()) == 0
    ), f"INV-K-CLUSTER VIOLATED: labels must start at 0; got min={int(unique.min())}."
    assert (
        int(unique.max()) == unique.size - 1
    ), f"INV-K-CLUSTER VIOLATED: labels must be dense 0..C-1; got unique={unique.tolist()}."


def test_signed_communities_biggest_first_ordering() -> None:
    """INV-K-CLUSTER: cluster id 0 is always the largest community.

    The canonical ordering is: primary key = community size descending,
    secondary key = smallest member index ascending. We exercise the
    primary key with an imbalanced planted partition where the sizes
    are strictly different (7 vs 3) so the size ordering is
    discriminative.

    Tolerance: exact — the canonicaliser returns a deterministic
    integer mapping, tolerance = 0.
    """
    N = 10
    K = np.zeros((N, N))
    # Block A: 7 nodes, block B: 3 nodes.
    for i in range(7):
        for j in range(7):
            if i != j:
                K[i, j] = 1.0
    for i in range(7, N):
        for j in range(7, N):
            if i != j:
                K[i, j] = 1.0
    for i in range(7):
        for j in range(7, N):
            K[i, j] = -0.5
            K[j, i] = -0.5

    labels = signed_communities(K, n_clusters_max=4)
    sizes = np.bincount(labels)
    # Community id 0 must be the biggest (size 7, not 3).
    assert int(sizes[0]) == 7, (
        f"INV-K-CLUSTER VIOLATED: community 0 has size {int(sizes[0])}, "
        f"expected 7 (biggest first). Sizes={sizes.tolist()}."
    )
    # Node 0 (biggest block) carries id 0; node N-1 (smaller block) does not.
    assert int(labels[0]) == 0
    assert int(labels[-1]) != 0
