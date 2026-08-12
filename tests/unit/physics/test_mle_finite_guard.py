# SPDX-License-Identifier: MIT
"""INV-LE1 fail-closed finite-output guard for the Rosenstein MLE.

The Rosenstein (1993) maximal-Lyapunov-exponent estimator measures the
exponential divergence rate of nearest-neighbor pairs in a delay-embedded
phase space. The estimate is only defined when there *is* divergence to
measure: §2.2 of Rosenstein et al. requires non-degenerate neighbor
distances. A constant / zero-variance / all-zeros / two-value-collapsed
series collapses every embedded point onto a single location, so every
pair distance is 0, ln(0) = −∞, and the slope fit is undefined. A series
carrying NaN/±Inf is likewise undefined.

The historic implementation *masked* these cases by silently returning
0.0 — a value that downstream Kelly sizing and risk gating read as
"λ ≤ 0 ⇒ stable regime". A frozen or corrupt series is NOT a stable
regime; it is an absence of measurable dynamics. This battery locks the
corrected contract:

* INV-LE2 qualitative anchors survive — logistic-map chaos ⇒ λ > 0,
  damped oscillator ⇒ λ < 0 (the guard must not perturb valid series).
* Dirty-data inputs FAIL CLOSED — each raises ``ValueError`` naming
  INV-LE1, rather than returning NaN/−∞/spurious-0.0.
* A low-SNR white-noise variance sweep stays FINITE and bounded — the
  guard must not over-trigger on legitimately small but non-degenerate
  signals.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.physics.lyapunov_exponent import _MAX_SERIES_LENGTH, maximal_lyapunov_exponent

# ---------------------------------------------------------------------------
# INV-LE2 qualitative anchors — the guard must preserve correct dynamics
# ---------------------------------------------------------------------------


def test_inv_le2_logistic_chaos_positive() -> None:
    """INV-LE2: the logistic map at r=4 is maximally chaotic ⇒ λ > 0.

    Theoretical λ = ln(2) ≈ 0.693. The finite-output guard must not
    suppress a genuinely positive divergence rate.
    """
    n = 2000
    logistic = np.empty(n, dtype=np.float64)
    logistic[0] = 0.1
    for i in range(1, n):
        logistic[i] = 4.0 * logistic[i - 1] * (1.0 - logistic[i - 1])
    mle = maximal_lyapunov_exponent(logistic, dim=2, tau=1, max_divergence_steps=20)
    assert math.isfinite(mle), f"INV-LE1: logistic MLE non-finite ({mle})"
    assert mle > 0.0, (
        f"INV-LE2 VIOLATED: logistic-map MLE={mle:.4f} ≤ 0. "
        f"Expected λ ≈ ln(2)={math.log(2.0):.4f} > 0 for r=4 chaos."
    )


def test_inv_le2_stable_contracting_negative() -> None:
    """INV-LE2: a stable contracting map (logistic r=2.8 → fixed point) ⇒ λ < 0.

    Fixture is a genuine converging dynamical system whose nearby-trajectory
    divergence decays as a CLEAN exponential, so Rosenstein has a real linear
    scaling region (R² ≈ 1.0) and INV-LE3's gate passes. (A lightly-damped
    sinusoid exp(-0.1t)·sin(t) is quasi-periodic, NOT a clean attractor: its
    log-divergence fit is R² ≈ 0.32, so INV-LE3 correctly demotes it — see
    test_inv_le3_nonscaling_demoted. INV-LE2 is thus exercised on a fixture
    where the method is actually valid.)
    """
    n = 2000
    stable = np.empty(n, dtype=np.float64)
    stable[0] = 0.3
    for i in range(1, n):
        stable[i] = 2.8 * stable[i - 1] * (1.0 - stable[i - 1])
    mle = maximal_lyapunov_exponent(stable, dim=3, tau=5)
    assert math.isfinite(mle), f"INV-LE1: stable MLE non-finite ({mle})"
    assert mle < 0.0, (
        f"INV-LE2 VIOLATED: stable contracting-map MLE={mle:.4f} ≥ 0. "
        "Expected λ < 0 for a converging trajectory (logistic r=2.8 fixed point)."
    )


def test_inv_le3_nonscaling_demoted() -> None:
    """INV-LE3: a quasi-periodic damped sinusoid is NOT a Rosenstein scaling
    region (R² < R2_MIN) ⇒ the estimator fails closed to the 0.0 sentinel
    rather than returning an unreliable slope."""
    n = 2000
    t = np.linspace(0.0, 100.0, n)
    damped = np.exp(-0.1 * t) * np.sin(t)
    diag: dict[str, float] = {}
    mle = maximal_lyapunov_exponent(damped, dim=3, tau=5, diagnostics=diag)
    assert diag["r_squared"] < 0.80, (
        f"fixture must be non-scaling for this test; R²={diag['r_squared']:.3f}"
    )
    assert diag["scaling_ok"] == 0.0 and mle == 0.0, (
        f"INV-LE3 VIOLATED: non-scaling input not demoted. "
        f"mle={mle}, scaling_ok={diag['scaling_ok']}, R²={diag['r_squared']:.3f}."
    )


def test_inv_le2_chaos_exceeds_damped() -> None:
    """INV-LE2 ordering: chaotic divergence dominates damped convergence."""
    n = 2000
    logistic = np.empty(n, dtype=np.float64)
    logistic[0] = 0.1
    for i in range(1, n):
        logistic[i] = 4.0 * logistic[i - 1] * (1.0 - logistic[i - 1])
    mle_chaos = maximal_lyapunov_exponent(logistic, dim=2, tau=1, max_divergence_steps=20)

    t = np.linspace(0.0, 100.0, n)
    damped = np.exp(-0.1 * t) * np.sin(t)
    mle_damped = maximal_lyapunov_exponent(damped, dim=3, tau=5)

    assert mle_chaos > mle_damped, (
        f"INV-LE2 VIOLATED: chaos MLE={mle_chaos:.4f} ≤ damped MLE={mle_damped:.4f}."
    )


# ---------------------------------------------------------------------------
# DIRTY-DATA fail-closed — each MUST raise, NOT return NaN/−inf/spurious 0.0
# ---------------------------------------------------------------------------


def test_fail_closed_constant_series() -> None:
    """A constant series has no divergence to measure ⇒ raise."""
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(np.full(600, 7.5, dtype=np.float64), dim=3, tau=1)


def test_fail_closed_zero_variance_series() -> None:
    """Zero-variance (single repeated value) ⇒ raise, not λ=0."""
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(np.full(512, -3.2, dtype=np.float64), dim=4, tau=2)


def test_fail_closed_all_zeros() -> None:
    """All-zeros is the canonical zero-variance degenerate input ⇒ raise."""
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(np.zeros(600, dtype=np.float64), dim=3, tau=1)


def test_fail_closed_two_point_degenerate() -> None:
    """A two-point series cannot be delay-embedded ⇒ raise (too short)."""
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(np.array([0.0, 1.0], dtype=np.float64), dim=3, tau=1)


def test_fail_closed_two_value_collapsed() -> None:
    """Two-value alternation collapses to zero divergence under Theiler ⇒ raise."""
    series = np.tile([0.0, 1.0], 300).astype(np.float64)
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_fail_closed_nan_embedded() -> None:
    """A NaN anywhere in the series ⇒ raise (undefined embedding)."""
    rng = np.random.default_rng(seed=3)
    series = rng.normal(0.0, 1.0, size=600)
    series[123] = np.nan
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_fail_closed_posinf_embedded() -> None:
    """A +Inf anywhere in the series ⇒ raise, NOT a bogus finite MLE."""
    rng = np.random.default_rng(seed=4)
    series = rng.normal(0.0, 1.0, size=600)
    series[200] = np.inf
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_fail_closed_neginf_embedded() -> None:
    """A −Inf anywhere in the series ⇒ raise."""
    rng = np.random.default_rng(seed=5)
    series = rng.normal(0.0, 1.0, size=600)
    series[10] = -np.inf
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_fail_closed_never_returns_nonfinite() -> None:
    """Cross-check: every dirty input RAISES — none slips through as NaN/±Inf.

    The contract is that the estimator NEVER returns a non-finite float; the
    only permitted reaction to a degenerate input is a fail-closed raise.
    """
    rng = np.random.default_rng(seed=9)
    nan_series = rng.normal(0.0, 1.0, size=600)
    nan_series[1] = np.nan
    dirty: list[np.ndarray] = [
        np.full(600, 42.0, dtype=np.float64),
        np.zeros(600, dtype=np.float64),
        np.tile([0.0, 1.0], 300).astype(np.float64),
        nan_series,
    ]
    for series in dirty:
        with pytest.raises(ValueError, match="INV-LE1"):
            maximal_lyapunov_exponent(series, dim=3, tau=1)


# ---------------------------------------------------------------------------
# Property / fuzz — low-SNR white noise stays FINITE and bounded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variance", [1e-12, 1e-11, 1e-9, 1e-6, 1e-4, 1e-3])
def test_low_snr_noise_sweep_finite_and_bounded(variance: float) -> None:
    """INV-LE1: a non-degenerate low-variance white-noise series stays finite.

    The guard must not over-trigger: genuine (if tiny) stochastic structure
    has measurable divergence. The MLE of scaled white noise is invariant to
    the variance (a global scale adds a constant ln(scale) offset that cancels
    in the slope), so it must be finite AND bounded across nine orders of
    magnitude of σ².
    """
    sigma = math.sqrt(variance)
    rng = np.random.default_rng(seed=2024)
    series = rng.normal(0.0, sigma, size=400)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    assert math.isfinite(mle), (
        f"INV-LE1 VIOLATED: white-noise σ²={variance:.0e} gave non-finite "
        f"MLE={mle}. A non-degenerate stochastic series must yield a finite λ."
    )
    # A scalar white-noise divergence rate is small and O(1)-bounded; a value
    # outside this envelope would signal a numerical blow-up, not physics.
    assert abs(mle) < 10.0, (
        f"INV-LE1 bound VIOLATED: white-noise σ²={variance:.0e} gave "
        f"|MLE|={abs(mle):.4f} ≥ 10 — implausible for a bounded noise series."
    )


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    log10_var=st.floats(min_value=-12.0, max_value=-3.0, allow_nan=False, allow_infinity=False),
    n=st.integers(min_value=100, max_value=400),
)
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_low_snr_noise_fuzz_finite(seed: int, log10_var: float, n: int) -> None:
    """Fuzz the low-SNR variance sweep: MLE is always a bounded finite real."""
    sigma = math.sqrt(10.0**log10_var)
    rng = np.random.default_rng(seed=seed)
    series = rng.normal(0.0, sigma, size=n)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    assert math.isfinite(mle), (
        f"INV-LE1 VIOLATED: seed={seed}, σ²=1e{log10_var:.1f}, n={n} ⇒ MLE={mle}."
    )
    assert abs(mle) < 10.0, (
        f"INV-LE1 bound VIOLATED: seed={seed}, σ²=1e{log10_var:.1f}, n={n} ⇒ "
        f"|MLE|={abs(mle):.4f} ≥ 10."
    )


def test_kdtree_nearest_neighbor_is_exact_vs_bruteforce() -> None:
    """The k-d tree Theiler-windowed NN selection must reproduce the brute-force
    argmin exactly, so the O(n log n) path yields the identical divergence curve
    (and thus identical lambda) as the former O(n^2) search."""
    import math

    import numpy as np
    from scipy.spatial import cKDTree

    from core.physics.lyapunov_exponent import delay_embed

    rng = np.random.default_rng(11)
    x = rng.normal(size=500)
    emb = delay_embed(x, dim=3, tau=1)
    ncand = emb.shape[0] - 60
    w = 3

    # brute force
    bf = []
    for i in range(ncand):
        d = np.sqrt(((emb[:ncand] - emb[i]) ** 2).sum(1))
        mask = np.abs(np.arange(ncand) - i) < w
        d[mask] = np.inf
        d[i] = np.inf
        bf.append(int(np.argmin(d)) if np.isfinite(d.min()) else -1)

    # k-d tree, k = 2w+2 guarantee
    tree = cKDTree(emb[:ncand])
    k = min(ncand, 2 * w + 2)
    dd, ii = tree.query(emb[:ncand], k=k)
    kd = []
    for i in range(ncand):
        j = -1
        for c in range(k):
            cand = int(ii[i, c])
            if abs(cand - i) >= w and cand != i and math.isfinite(dd[i, c]):
                j = cand
                break
        kd.append(j)

    assert kd == bf, "k-d tree NN selection must match brute-force exactly"


# ---------------------------------------------------------------------------
# DS-16 availability guard — over-long series is REFUSED fast, not hung
# ---------------------------------------------------------------------------


def test_ds16_over_length_series_fails_closed_fast() -> None:
    """DS-16 repro: a series one sample over the cap must RAISE in << 1 s.

    The destroyer finding was that ``maximal_lyapunov_exponent`` runs an
    O(N²/4) pure-Python divergence loop with no length cap, so a 100k-sample
    series hangs ~3–4 h (availability/DoS). The guard must refuse BEFORE any
    divergence work. We size the series just over the default cap (which would
    itself be a multi-minute run if it were allowed to proceed) and assert the
    raise returns effectively instantly.
    """
    over = np.zeros(_MAX_SERIES_LENGTH + 1, dtype=np.float64)
    over[::3] = 1.0  # non-degenerate content so ONLY the length guard can fire
    t0 = time.perf_counter()
    with pytest.raises(ValueError, match="exceeds max"):
        maximal_lyapunov_exponent(over, dim=3, tau=1)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, (
        f"DS-16 VIOLATED: over-length refusal took {elapsed:.3f}s ≥ 1s — the "
        "length guard must fire before the O(N²) divergence loop, not after."
    )


def test_ds16_custom_cap_refuses_and_default_unchanged() -> None:
    """DS-16: an explicit ``max_series_length`` refuses above the custom cap,
    while a series inside the custom cap (and inside the default) still runs.
    """
    rng = np.random.default_rng(seed=7)
    series = rng.normal(0.0, 1.0, size=300)
    # 300 > custom cap 100 ⇒ refuse under the tightened cap …
    with pytest.raises(ValueError, match="exceeds max 100"):
        maximal_lyapunov_exponent(series, dim=3, tau=1, max_series_length=100)
    # … but the SAME series is well inside the default cap and computes fine.
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    assert math.isfinite(mle)
    # A non-positive custom cap is itself a contract violation (fail-closed).
    with pytest.raises(ValueError, match="max_series_length must be positive"):
        maximal_lyapunov_exponent(series, dim=3, tau=1, max_series_length=0)


def test_ds16_in_range_series_returns_prefix_value_bit_for_bit() -> None:
    """DS-16 non-vacuous negative: an in-range series returns the SAME MLE as
    before the guard existed — bit-for-bit against a pre-fix computed value.

    The guard is a top-of-function refusal branch; it must NOT touch the math
    for any legitimate in-range input. Reference computed on the unmodified
    estimator: logistic map (r=4, x0=0.1, n=800), dim=2, tau=1,
    max_divergence_steps=20 ⇒ λ ≈ ln 2. Any drift here means the guard
    perturbed a valid computation.
    """
    n = 800
    x = np.empty(n, dtype=np.float64)
    x[0] = 0.1
    for i in range(1, n):
        x[i] = 4.0 * x[i - 1] * (1.0 - x[i - 1])
    assert x.size <= _MAX_SERIES_LENGTH  # fixture is genuinely in-range
    mle = maximal_lyapunov_exponent(x, dim=2, tau=1, max_divergence_steps=20)
    PREFIX_REFERENCE = 0.6941559179641292
    assert mle == PREFIX_REFERENCE, (
        f"DS-16 VIOLATED: in-range MLE={mle!r} != pre-fix {PREFIX_REFERENCE!r}. "
        "The length guard must preserve every in-range result bit-for-bit."
    )
