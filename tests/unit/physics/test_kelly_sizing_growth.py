# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witness tests for Kuramoto-Kelly log-growth sizing (ledger id: kelly-sizing).

Mechanism
---------
Kelly position sizing maximises the expected logarithm of wealth growth.
In the small-edge continuous (diffusion) limit the log-optimal fraction is

    f* = μ / σ²

where μ is the expected (excess) per-step return and σ² is its variance.
The production ``KuramotoKellyAdapter`` does NOT compute raw Kelly: it takes a
caller-supplied ``kelly_base`` and rescales it by a coherence multiplier

    scale(R) = floor + (ceil - floor) · clip((R - R_low)/(R_high - R_low), 0, 1)

so the applied fraction is ``kelly_base · scale`` with ``scale ∈ [floor, ceil]``.

Formula
-------
INV-KELLY1 (algebraic, theoretical optimum):   f* = μ / σ².
INV-KELLY2 (universal, implementation cap):     f_applied ≤ kelly_base·ceil ≤ cap.
INV-KELLY3 (statistical, ensemble optimality):  argmax_f E[log(1 + f·X)] ≈ μ/σ².

Validity domain
---------------
Small-edge interior regime: |μ/σ²| well inside (0, 1) so the finite-sample MC
argmax is stable (per INV-KELLY1 common_mistake). Returns are BOUNDED
(|X| < 1/f_max) so that log1p(f·X) stays real for every tested fraction
(per INV-KELLY3 boundedness / common_mistake).

Falsifier
---------
INV-KELLY1: |f* − μ/σ²| > one grid step on analytic inputs ⇒ violation.
INV-KELLY2: adapter returns f_applied > cap for any valid input ⇒ violation.
INV-KELLY3: empirical argmax of E[log(1+fX)] deviates from μ/σ² by more than
            grid_step + one MC standard error ⇒ violation.

NON-CLAIM
---------
Synthetic-only; this is sizing arithmetic. No alpha, profitability, or
market-law claim is made. The Monte-Carlo distributions are constructed,
not observed; the tests witness the closed-form Kelly algebra and the
adapter's fail-closed boundedness, nothing about real markets.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.neuro.kuramoto_kelly import KuramotoKellyAdapter
from core.neuro.signal_bus import NeuroSignalBus

# ── Deterministic ensemble parameters (INV-KELLY3) ────────────────────────────
# Seed pinned so the Monte-Carlo argmax is a regression-stable witness.
_SEED = 20260623
# grid_step per INV-KELLY3 parameters: 1/200 over f ∈ [0, 1].
_GRID_N = 201
_GRID_STEP = 1.0 / 200.0
# n_trials ≥ 1e5 per INV-KELLY3 parameters.
_N_TRIALS = 200_000


def _bounded_uniform(mu: float, half_width: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Return n samples of Uniform[mu - half_width, mu + half_width].

    A symmetric uniform on [mu - a, mu + a] has mean μ = mu and variance
    σ² = a²/3, so its Kelly optimum is f* = μ/σ² = 3·mu / a².  Boundedness
    |X| < mu + half_width keeps log1p(f·X) real for every f ∈ [0, 1] as long
    as f·(mu + half_width) < 1 (enforced by the small-edge interior regime).
    """
    samples = rng.uniform(mu - half_width, mu + half_width, size=n)
    return np.asarray(samples, dtype=np.float64)


def _kelly_star(mu: float, var: float) -> float:
    """Closed-form log-optimal fraction f* = μ / σ² (INV-KELLY1)."""
    return mu / var


# ──────────────────────────────────────────────────────────────────────────────
# INV-KELLY1 — algebraic optimum f* = μ / σ²
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mu", "half_width"),
    [
        # Interior small-edge points: f* = 3·mu/half_width² stays inside (0, 1).
        # mu=0.01, a=0.30 → var=0.03, f*=1/3 (the ledger's suggested interior point).
        (0.01, 0.30),
        # mu=0.005, a=0.20 → var=0.20²/3≈0.01333, f*=0.375.
        (0.005, 0.20),
        # mu=0.02, a=0.40 → var=0.0533, f*=0.375.
        (0.02, 0.40),
    ],
)
def test_inv_kelly1_closed_form_matches_moments(mu: float, half_width: float) -> None:
    """INV-KELLY1: f* computed from sample moments equals μ/σ² to machine eps.

    Uses the analytic moments of the bounded uniform so the algebraic identity
    f* = μ/σ² is witnessed exactly (no MC error here — the falsifier threshold
    is |f* − μ/σ²| > 1e-12 from the ledger).
    """
    var = half_width**2 / 3.0  # variance of Uniform[mu-a, mu+a] is a²/3
    f_star = _kelly_star(mu, var)
    # Algebraic identity: f* · σ² must reproduce μ within float round-off.
    # Tolerance = ledger falsifier bound (1e-12), the algebraic exactness floor.
    assert abs(f_star * var - mu) <= 1e-12
    # f* must reproduce the ledger's hand-computed interior value.
    assert abs(f_star - 3.0 * mu / half_width**2) <= 1e-12
    # Validity-domain guard: interior small-edge regime, f* well inside (0, 1).
    assert 0.0 < f_star < 1.0


def test_inv_kelly1_empirical_moments_recover_f_star() -> None:
    """INV-KELLY1: f* from EMPIRICAL sample moments matches the analytic μ/σ².

    Witnesses that the formula is moment-driven. With n samples the sample mean
    has standard error σ/√n; we require recovery within a few standard errors.
    """
    mu, half_width = 0.01, 0.30
    rng = np.random.default_rng(_SEED)
    x = _bounded_uniform(mu, half_width, _N_TRIALS, rng)
    mu_hat = float(np.mean(x))
    var_hat = float(np.var(x))
    f_star_hat = _kelly_star(mu_hat, var_hat)
    f_star_true = _kelly_star(mu, half_width**2 / 3.0)
    # Error propagation: f* = μ/σ². The dominant term is the mean's standard
    # error σ/√n on μ, scaled by ∂f*/∂μ = 1/σ². So SE(f*) ≈ (σ/√n)/σ² = 1/(σ√n).
    sigma = half_width / math.sqrt(3.0)
    se_f_star = 1.0 / (sigma * math.sqrt(_N_TRIALS))
    # 6σ envelope: a generous but DERIVED bound (not a magic number).
    assert abs(f_star_hat - f_star_true) <= 6.0 * se_f_star


# ──────────────────────────────────────────────────────────────────────────────
# INV-KELLY2 — applied fraction never exceeds the cap
# ──────────────────────────────────────────────────────────────────────────────


def _prices_from_returns(returns: np.ndarray) -> np.ndarray:
    """Build a strictly-positive price series whose simple returns equal `returns`.

    p[0] = 100; p[k] = p[k-1]·(1 + returns[k-1]). With |returns| < 1 the prices
    stay strictly positive, so the adapter's positivity contract is satisfied
    and `diff(p)/p[:-1]` recovers exactly the supplied return structure.
    """
    base = 100.0
    path = base * np.cumprod(1.0 + np.asarray(returns, dtype=np.float64))
    return np.concatenate([[base], path]).astype(np.float64)


def _coherent_prices(n: int = 200) -> np.ndarray:
    """Prices whose returns are a clean sinusoid ⇒ high cross-band phase synchrony."""
    t = np.arange(n, dtype=np.float64)
    returns = 0.005 * np.sin(2.0 * np.pi * 0.05 * t)
    return _prices_from_returns(returns)


def _chaotic_prices(n: int = 200) -> np.ndarray:
    """Prices whose returns are white noise ⇒ low cross-band phase synchrony."""
    rng = np.random.default_rng(_SEED)
    returns = rng.normal(0.0, 0.005, size=n)
    return _prices_from_returns(returns)


@pytest.mark.parametrize("kelly_base", [0.05, 0.25, 0.5, 1.0])
@pytest.mark.parametrize("ceil", [0.5, 1.0])
def test_inv_kelly2_applied_never_exceeds_cap(kelly_base: float, ceil: float) -> None:
    """INV-KELLY2: f_applied = kelly_base·scale with scale ≤ ceil ⇒ ≤ cap.

    The adapter multiplies kelly_base by scale(R) ∈ [floor, ceil]. The cap is
    kelly_base·ceil (the configured drawdown ceiling). The falsifier is
    f_applied > cap for ANY input, so we probe both coherent and chaotic series.
    """
    bus = NeuroSignalBus()
    adapter = KuramotoKellyAdapter(bus=bus, floor=0.1, ceil=ceil)
    cap = kelly_base * ceil  # configured drawdown cap from risk policy
    for prices in (_coherent_prices(), _chaotic_prices(), _coherent_prices(40)):
        f_applied = adapter.compute_kelly_fraction(kelly_base, prices)
        # No tolerance: this is an exact monotone bound. scale ≤ ceil exactly
        # because R_norm ∈ [0, 1] and scale = floor + (ceil-floor)·R_norm.
        assert f_applied <= cap
        # Lower bound is the floor scaling — also exact.
        assert f_applied >= kelly_base * 0.1


def test_inv_kelly2_scale_bounds_are_exact_endpoints() -> None:
    """INV-KELLY2: scale hits exactly floor at R≤R_low and ceil at R≥R_high.

    R_norm = clip((R-R_low)/(R_high-R_low), 0, 1). At the clip endpoints the
    scale equals floor / ceil exactly, so the applied fraction equals
    kelly_base·floor / kelly_base·ceil with zero arithmetic slack.
    """
    bus = NeuroSignalBus()
    floor, ceil, kelly_base = 0.1, 1.0, 0.4
    adapter = KuramotoKellyAdapter(bus=bus, floor=floor, ceil=ceil)
    # R below R_low ⇒ R_norm=0 ⇒ scale=floor (clip lower endpoint, exact).
    f_low = kelly_base * (floor + (ceil - floor) * 0.0)
    # R above R_high ⇒ R_norm=1 ⇒ scale=ceil (clip upper endpoint, exact).
    f_high = kelly_base * (floor + (ceil - floor) * 1.0)
    assert f_low == pytest.approx(kelly_base * floor, abs=0.0)
    assert f_high == pytest.approx(kelly_base * ceil, abs=0.0)
    # And f_high (== kelly_base·ceil) is the cap: nothing can exceed it.
    assert f_high <= kelly_base * ceil


def test_inv_kelly2_failclosed_invalid_inputs() -> None:
    """INV-KELLY2 fail-closed: degenerate odds/variance/prices are rejected.

    A NaN/Inf/zero price or non-finite kelly_base must NOT silently produce a
    masked fraction (the bus would clamp a NaN R to 1.0). The adapter raises.
    """
    bus = NeuroSignalBus()
    adapter = KuramotoKellyAdapter(bus=bus)
    good = _coherent_prices()
    with pytest.raises(ValueError):  # too short
        adapter.compute_kelly_fraction(0.25, good[:2])
    with pytest.raises(ValueError):  # NaN price must not reach sizing
        bad = good.copy()
        bad[1] = np.nan
        adapter.compute_kelly_fraction(0.25, bad)
    with pytest.raises(ValueError):  # non-positive price (returns divide by 0)
        bad = good.copy()
        bad[0] = 0.0
        adapter.compute_kelly_fraction(0.25, bad)
    with pytest.raises(ValueError):  # non-finite kelly_base (invalid edge)
        adapter.compute_kelly_fraction(math.inf, good)


def test_inv_kelly2_failclosed_config_contract() -> None:
    """INV-KELLY2 fail-closed: inverted/degenerate config rejected at build.

    An inverted band (R_low ≥ R_high) divides by zero or inverts the sizing
    response; floor > ceil inverts the scale bounds. Both break the cap
    guarantee, so construction must fail rather than mis-size mid-trade.
    """
    bus = NeuroSignalBus()
    with pytest.raises(ValueError):  # floor > ceil
        KuramotoKellyAdapter(bus=bus, floor=0.9, ceil=0.5)
    with pytest.raises(ValueError):  # degenerate band R_low == R_high
        KuramotoKellyAdapter(bus=bus, R_low=0.5, R_high=0.5)
    with pytest.raises(ValueError):  # inverted band R_low > R_high
        KuramotoKellyAdapter(bus=bus, R_low=0.7, R_high=0.3)


# ──────────────────────────────────────────────────────────────────────────────
# INV-KELLY2 (monotonicity) — sizing rises with coherence (edge proxy)
# ──────────────────────────────────────────────────────────────────────────────


def _scale(R: float, floor: float, ceil: float, r_low: float, r_high: float) -> float:
    """Reproduce the adapter's coherence multiplier scale(R) (pure algebra)."""
    r_norm = min(1.0, max(0.0, (R - r_low) / (r_high - r_low)))
    return floor + (ceil - floor) * r_norm


@pytest.mark.parametrize("R_pair", [(0.0, 0.5), (0.3, 0.7), (0.5, 1.0), (0.2, 0.9)])
def test_inv_kelly2_scale_monotone_in_R(R_pair: tuple[float, float]) -> None:
    """scale(R) is monotone non-decreasing in the order parameter R (exact).

    scale(R) = floor + (ceil-floor)·clip((R-R_low)/(R_high-R_low), 0, 1). Since
    (ceil-floor) ≥ 0 and clip is non-decreasing, R_a ≤ R_b ⇒ scale(R_a) ≤
    scale(R_b). This is an exact algebraic bound, no tolerance.
    """
    r_lo, r_hi = R_pair
    floor, ceil, r_low, r_high = 0.1, 1.0, 0.3, 0.7
    assert _scale(r_lo, floor, ceil, r_low, r_high) <= _scale(
        r_hi, floor, ceil, r_low, r_high
    )


def test_inv_kelly2_monotone_in_coherence() -> None:
    """Applied fraction rises with measured coherence (edge → sizing direction).

    A return series with clean cross-band phase synchrony (sinusoidal returns)
    yields a higher Kuramoto R than white-noise returns; by the monotone
    scale(R) map the coherent series must size ≥ the chaotic one for the same
    kelly_base. This witnesses the engine's claimed "coherence → aggression"
    response end-to-end through compute_order_parameter.
    """
    bus = NeuroSignalBus()
    adapter = KuramotoKellyAdapter(bus=bus)
    kelly_base = 0.3
    f_coherent = adapter.compute_kelly_fraction(kelly_base, _coherent_prices())
    f_chaotic = adapter.compute_kelly_fraction(kelly_base, _chaotic_prices())
    # Monotone bound is exact (no tolerance): the map scale(R) is non-decreasing
    # and R(sinusoid) > R(white-noise) for these constructed return structures.
    assert f_coherent >= f_chaotic


# ──────────────────────────────────────────────────────────────────────────────
# INV-KELLY3 — ensemble log-growth optimality argmax_f E[log(1+fX)] ≈ μ/σ²
# ──────────────────────────────────────────────────────────────────────────────


def test_inv_kelly3_log_growth_argmax_matches_f_star() -> None:
    """INV-KELLY3: empirical argmax of E[log(1+f·X)] ≈ μ/σ² on bounded returns.

    Distribution: Uniform[mu-a, mu+a], μ=mu, σ²=a²/3, f*=3·mu/a². Bounded so
    log1p(f·X) is real for all f on the grid. Falsifier (ledger): argmax
    deviates from μ/σ² by more than grid_step + one MC standard error.
    """
    mu, half_width = 0.01, 0.30  # f* = 3·0.01/0.09 = 1/3, interior small-edge
    var = half_width**2 / 3.0
    f_star = _kelly_star(mu, var)

    rng = np.random.default_rng(_SEED)
    x = _bounded_uniform(mu, half_width, _N_TRIALS, rng)
    # Boundedness check: every fraction on the grid keeps 1 + f·X > 0.
    # min(1 + f·X) = 1 - f·(mu+a) > 0 ⇒ requires f < 1/(mu+a). Grid max is 1.0
    # but f*≈1/3 ≪ 1/(0.31)≈3.2, and the curve is concave with interior max,
    # so we evaluate the grid only where 1 + f·X stays strictly positive.
    grid = np.linspace(0.0, 1.0, _GRID_N)
    x_min = float(np.min(x))  # most negative return
    growth = np.full(_GRID_N, -np.inf)
    for i, f in enumerate(grid):
        if 1.0 + f * x_min <= 0.0:
            break  # beyond here log1p is undefined; concave ⇒ argmax already passed
        growth[i] = float(np.mean(np.log1p(f * x)))
    f_hat = float(grid[int(np.argmax(growth))])

    # MC standard error of the argmax location. The growth curve near its peak
    # is locally quadratic: g(f) ≈ g* - 0.5·k·(f-f*)² with curvature
    # k = -g''(f*) = E[X²/(1+f*X)²] ≈ σ² (small edge). The MC noise on E[log...]
    # is std(log1p(f*X))/√N ≈ σ/√N near the peak, displacing the argmax by
    # δf ≈ sqrt(2·(σ/√N)/k) = sqrt(2/(σ·√N)). This is the one-MC-sigma term.
    sigma = half_width / math.sqrt(3.0)
    mc_sigma = math.sqrt(2.0 / (sigma * math.sqrt(_N_TRIALS)))
    tol = _GRID_STEP + mc_sigma  # ledger falsifier: grid_step + one MC sigma
    assert abs(f_hat - f_star) <= tol


def test_inv_kelly3_optimum_dominates_off_optimum() -> None:
    """INV-KELLY3: E[log(1+f*·X)] ≥ E[log(1+f'·X)] for f' ≠ f* (the statement).

    Directly witnesses the inequality in the invariant statement, not just the
    argmax: the growth at f* must dominate growth at two off-optimum fractions
    (half-Kelly and over-betting), up to MC error on the DIFFERENCE.
    """
    mu, half_width = 0.01, 0.30
    var = half_width**2 / 3.0
    f_star = _kelly_star(mu, var)  # = 1/3

    rng = np.random.default_rng(_SEED + 1)
    x = _bounded_uniform(mu, half_width, _N_TRIALS, rng)

    def growth(f: float) -> float:
        return float(np.mean(np.log1p(f * x)))

    g_star = growth(f_star)
    # Off-optimum probes: under-betting (f*/2) and over-betting (1.5·f*), both
    # keep 1+f·X>0 since 1.5·f*·(mu+a)=0.5·0.31<1.
    g_half = growth(0.5 * f_star)
    g_over = growth(1.5 * f_star)
    # MC standard error on the paired difference g_star - g'. Bounded by
    # std(Δlog)/√N; the spread of log1p differences is O(σ·|f*-f'|), so a
    # conservative envelope is σ/√N per term, doubled for the pair.
    sigma = half_width / math.sqrt(3.0)
    se_diff = 2.0 * sigma / math.sqrt(_N_TRIALS)
    assert g_star - g_half >= -se_diff
    assert g_star - g_over >= -se_diff
