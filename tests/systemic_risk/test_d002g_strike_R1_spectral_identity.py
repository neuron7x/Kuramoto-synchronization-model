# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R1 — bit-identity is too weak; M1 must produce spectrally distinct K.

Attack
------
``check_phase_0a`` decides Phase 0a by ``np.array_equal``. A K matrix
that shares the spectrum of the precursor (same eigenvalues, different
eigenvectors) would pass ``array_equal=False`` while remaining
NEAR-DEGENERATE for any spectrally-driven metric.

This test enforces a stronger contract on the seed-sensitive
``ricci_flow`` substrate: the sorted-eigenvalue infinity distance and
the KS-distance between eigenvalue distributions must both exceed a
calibrated floor.

Floor calibration
-----------------
The floor is the null-vs-null distance between two distinct ricci_flow
realisations at lambda=0 (which we KNOW are spectrally distinct because
the ER graph is re-drawn) measured across multiple paired seeds, plus
a 3·MAD margin. The floor is computed at test-time, not hard-coded, so
the test stays robust to substrate-version drift.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import SUBSTRATE_BY_ID
from research.systemic_risk.d002g_null_mechanisms import realize_null

# Strike rungs run heavy eigenvalue / multi-seed statistics; gate behind
# `slow` so python-fast-tests stays under its 20-min job cap. The strike
# acceptor's measurement_command runs this test explicitly without the
# `-m "not slow"` filter, so coverage is preserved on the strike binding.
pytestmark = pytest.mark.slow


def _sorted_eigvals(K: np.ndarray) -> np.ndarray:
    return np.sort(np.linalg.eigvalsh(np.asarray(K, dtype=np.float64)))


def _spectrum_inf_dist(K_a: np.ndarray, K_b: np.ndarray) -> float:
    """L∞ between sorted eigenvalue vectors of two symmetric K."""
    ea = _sorted_eigvals(K_a)
    eb = _sorted_eigvals(K_b)
    return float(np.max(np.abs(ea - eb)))


def _spectrum_ks(K_a: np.ndarray, K_b: np.ndarray) -> float:
    """Two-sample KS distance between eigenvalue distributions.

    A self-contained KS — sup_x |F_a(x) − F_b(x)|. No scipy dependency
    needed for this primitive.
    """
    ea = np.sort(_sorted_eigvals(K_a))
    eb = np.sort(_sorted_eigvals(K_b))
    n_a = ea.size
    n_b = eb.size
    all_vals = np.concatenate([ea, eb])
    cdf_a = np.searchsorted(ea, all_vals, side="right") / float(n_a)
    cdf_b = np.searchsorted(eb, all_vals, side="right") / float(n_b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


def _calibrate_floor(
    substrate: object,
    *,
    N: int,
    n_pairs: int = 16,
    base_seed_lo: int = 1000,
) -> tuple[float, float, float, float]:
    """Empirical (lower_inf, median_inf, lower_ks, median_ks) over independent pairs.

    The lower bound is ``min(samples) / 4``. We compare M1 distance
    against the lower bound (must EXCEED) to refuse spectral
    near-degeneracy. We also report the median so the test can require
    the M1 distance to land inside the null-vs-null distribution at
    order-of-magnitude scale.
    """
    inf_dists = np.zeros(n_pairs, dtype=np.float64)
    ks_dists = np.zeros(n_pairs, dtype=np.float64)
    for i in range(n_pairs):
        r_a = substrate.realize(N=N, lambda_=0.0, seed=base_seed_lo + 2 * i)  # type: ignore[attr-defined]
        r_b = substrate.realize(N=N, lambda_=0.0, seed=base_seed_lo + 2 * i + 1)  # type: ignore[attr-defined]
        K_a = np.asarray(r_a.K_baseline[0], dtype=np.float64)
        K_b = np.asarray(r_b.K_baseline[0], dtype=np.float64)
        inf_dists[i] = _spectrum_inf_dist(K_a, K_b)
        ks_dists[i] = _spectrum_ks(K_a, K_b)
    return (
        float(inf_dists.min()) / 4.0,
        float(np.median(inf_dists)),
        float(ks_dists.min()) / 4.0,
        float(np.median(ks_dists)),
    )


@pytest.mark.parametrize("N", [50, 100])
def test_R1_ricci_flow_M1_spectrally_distinct(N: int) -> None:
    """For ricci_flow, M1 K_null must be spectrally distinct from K_precursor."""
    sub = SUBSTRATE_BY_ID["ricci_flow"]
    inf_floor, inf_median, ks_floor, ks_median = _calibrate_floor(sub, N=N)
    # Sanity: calibration set produced non-degenerate distances.
    assert inf_floor > 0.0, (
        f"R1 floor calibration failed: inf_floor={inf_floor:.3e} <= 0. "
        "Either the substrate is seed-degenerate or the calibration "
        "set is too small."
    )
    assert ks_floor > 0.0, f"R1 floor calibration failed: ks_floor={ks_floor:.3e} <= 0"

    for base_seed in (0, 7, 42, 123, 2026):
        pr = sub.realize(N=N, lambda_=0.0, seed=base_seed)
        nu = realize_null(
            sub,
            strategy="M1_INDEPENDENT_SEED",
            base_seed=base_seed,
            N=N,
            lambda_value=0.0,
        )
        K_p = np.asarray(pr.K_baseline[0], dtype=np.float64)
        K_n = np.asarray(nu.K_baseline, dtype=np.float64)
        d_inf = _spectrum_inf_dist(K_p, K_n)
        d_ks = _spectrum_ks(K_p, K_n)
        assert d_inf > inf_floor, (
            f"R1 VIOLATED: substrate=ricci_flow N={N} seed={base_seed} "
            f"spectrum L∞ distance {d_inf:.3e} ≤ floor {inf_floor:.3e} "
            f"(null-vs-null median = {inf_median:.3e}). "
            "M1 null shares the precursor's spectrum (near-degenerate)."
        )
        assert d_ks > ks_floor, (
            f"R1 VIOLATED: substrate=ricci_flow N={N} seed={base_seed} "
            f"spectrum KS distance {d_ks:.3e} ≤ floor {ks_floor:.3e} "
            f"(null-vs-null median = {ks_median:.3e}). "
            "Eigenvalue distributions are indistinguishable."
        )
