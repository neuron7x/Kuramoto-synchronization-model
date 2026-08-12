# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for T2b — Stuart-Landau ES Proximity (Lee et al. PNAS 2025).

Invariants tested
-----------------
INV-SL1   amplitude ≥ 0  (universal)
INV-SL2   es_proximity ∈ [0, 1]  (universal)
INV-T2b   rolling ES peak precedes R(t) peak by τ ≥ 1 bar  (qualitative)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TypedDict

import numpy as np
import pytest
from numpy.typing import NDArray

import core.physics.stuart_landau_es as sl
from core.physics.stuart_landau_es import (
    StuartLandauResult,
    _analytic_signal,
    _estimate_growth_rate,
    _estimate_growth_rate_audit,
    _extract_amplitude_phase_omega,
    _hysteresis_sweep,
    _initial_state_from_seed,
    _validate_prices,
    _validate_sweep_config,
    _validate_z0,
    crisis_signal_sl,
    fit_stuart_landau,
    rolling_es_proximity,
)

pytestmark = pytest.mark.heavy_math


def _envelope_oscillator_prices(
    growth_rate: float,
    T: int = 96,
    N: int = 4,
    freq: float = 0.8,
    amp0: float = 0.01,
    seed: int = 0,
) -> NDArray[np.float64]:
    """Synthetic price panel whose log-return envelope grows/decays at ``growth_rate``.

    Each asset's log-returns are an exponential-envelope sinusoid
    r_j(t) = amp0 · e^{growth_rate · t} · sin(freq·t + φ_j) + tiny noise, so the
    Hilbert amplitude envelope A_j(t) ∝ e^{growth_rate · t} and the Stuart-Landau
    growth rate μ_j must recover ``growth_rate`` in sign:
        growth_rate < 0 → decaying (stable focus, μ < 0)
        growth_rate > 0 → growing (limit cycle, μ > 0).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(T - 1, dtype=np.float64)
    env = np.exp(growth_rate * t)
    log_rets = np.zeros((T - 1, N), dtype=np.float64)
    for j in range(N):
        log_rets[:, j] = (
            amp0 * env * np.sin(freq * t + j) + rng.standard_normal(T - 1) * 1e-5
        )
    prices: NDArray[np.float64] = np.empty((T, N), dtype=np.float64)
    prices[0, :] = 100.0
    prices[1:, :] = 100.0 * np.exp(np.cumsum(log_rets, axis=0))
    return prices


def test_mu_negative_for_stable_decaying_oscillator() -> None:
    """INV-SL1 substrate: decaying-envelope (stable focus) ⇒ growth rate μ < 0.

    Stuart-Landau μ is the linear growth rate (d ln|z|/dt). A stable focus has a
    decaying amplitude envelope, so the derived μ must be strictly negative —
    the genuine Hopf threshold is μ = 0, not the prior fabricated
    tanh(variance−0.5) map.
    """
    mus: list[float] = []
    for seed in range(6):
        prices = _envelope_oscillator_prices(growth_rate=-0.05, seed=seed)
        _, _, _, mu = _extract_amplitude_phase_omega(prices)
        mus.append(float(mu.max()))  # worst (least-negative) asset
    worst = max(mus)
    assert worst < 0.0, (
        f"INV-SL μ-growth-rate VIOLATED: stable decaying oscillator gave "
        f"max μ={worst:.6e} ≥ 0, expected μ<0 (decaying envelope = stable focus). "
        f"μ = OLS slope of ln amplitude envelope; Hopf threshold at μ=0. "
        f"Tested 6 seeds, growth_rate=-0.05, per-seed max μ={mus}."
    )


def test_mu_positive_for_growing_limit_cycle() -> None:
    """INV-SL1 substrate: growing-envelope (limit cycle) ⇒ growth rate μ > 0.

    A supercritical Hopf / limit cycle has a growing amplitude envelope, so the
    derived μ must be strictly positive, mirror-imaging the stable case about
    the μ=0 Hopf threshold.
    """
    mus: list[float] = []
    for seed in range(6):
        prices = _envelope_oscillator_prices(growth_rate=+0.05, seed=seed)
        _, _, _, mu = _extract_amplitude_phase_omega(prices)
        mus.append(float(mu.min()))  # worst (least-positive) asset
    worst = min(mus)
    assert worst > 0.0, (
        f"INV-SL μ-growth-rate VIOLATED: growing limit-cycle signal gave "
        f"min μ={worst:.6e} ≤ 0, expected μ>0 (growing envelope = limit cycle). "
        f"μ = OLS slope of ln amplitude envelope; Hopf threshold at μ=0. "
        f"Tested 6 seeds, growth_rate=+0.05, per-seed min μ={mus}."
    )


def test_mu_clamped_finite_and_bounded() -> None:
    """μ stays finite and within the ±1 Euler-stability clamp on all regimes.

    Guards that the growth-rate estimator never emits NaN/Inf and respects the
    numerical-stability bound feeding the Stuart-Landau RHS (|z|*=√μ ≤ 1), so
    INV-SL1/SL2 downstream cannot be corrupted by an unbounded μ.
    """
    bad: list[tuple[float, float]] = []
    n_t, n_assets = 8, 3
    t = np.arange(n_t, dtype=np.float64)
    # Directly build finite log-envelopes A=e^{rate·t}: short window keeps even
    # steep rates finite (exp(2·7)≈1.2e6), so the raw OLS slope == rate exactly.
    # This isolates the estimator+clamp from price-construction overflow.
    for raw_rate in (-2.0, -0.05, 0.0, 0.05, 2.0):
        envelope = np.tile(np.exp(raw_rate * t)[:, None], (1, n_assets))
        mu = _estimate_growth_rate(envelope)
        if not np.all(np.isfinite(mu)) or np.any(np.abs(mu) > 1.0 + 1e-12):
            bad.append((raw_rate, float(np.abs(mu).max())))
        # |rate|>1 must be clamped exactly to the ±1 band, sign preserved
        if abs(raw_rate) > 1.0 and not np.allclose(mu, np.sign(raw_rate) * 1.0):
            bad.append((raw_rate, float(np.abs(mu).max())))
    assert not bad, (
        f"INV-SL μ bound VIOLATED: μ non-finite, |μ|>1, or steep rate unclamped "
        f"in {len(bad)} cases. First: {bad[0] if bad else None}. "
        f"μ clamp = ±1 (Euler-stable, |z|*=√μ≤1). "
        f"Tested raw rates (-2,-0.05,0,0.05,2) × {n_assets} assets, n_t={n_t}."
    )


def test_price_contract_rejects_shape_finiteness_and_positivity() -> None:
    """Price contract guards every low-level shape/value branch explicitly."""
    with pytest.raises(ValueError, match="prices shape"):
        _validate_prices(np.ones(8, dtype=np.float64), min_T=8)
    with pytest.raises(ValueError, match="T>=8"):
        _validate_prices(np.ones((7, 2), dtype=np.float64), min_T=8)
    with pytest.raises(ValueError, match="N>=2"):
        _validate_prices(np.ones((8, 1), dtype=np.float64), min_T=8)

    nonfinite = np.ones((8, 2), dtype=np.float64)
    nonfinite[0, 0] = np.inf
    with pytest.raises(ValueError, match="prices must be finite"):
        _validate_prices(nonfinite, min_T=8)

    nonpositive = np.ones((8, 2), dtype=np.float64)
    nonpositive[0, 0] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        _validate_prices(nonpositive, min_T=8)


def test_sweep_config_rejects_invalid_bounds_counts_and_dt() -> None:
    """Sweep config guards finite K, ordered range, counts, and positive dt."""
    kwargs = dict(K_low=0.0, K_high=1.0, K_steps=3, int_steps=2, dt=0.05)
    _validate_sweep_config(**kwargs, source="test")

    for bad_low, bad_high in ((np.inf, 1.0), (0.0, np.inf), (2.0, 1.0)):
        with pytest.raises(ValueError, match="K_low|K_low<K_high"):
            _validate_sweep_config(
                K_low=bad_low,
                K_high=bad_high,
                K_steps=3,
                int_steps=2,
                dt=0.05,
                source="test",
            )

    with pytest.raises(ValueError, match="K_steps>=2"):
        _validate_sweep_config(**{**kwargs, "K_steps": 1}, source="test")
    with pytest.raises(ValueError, match="int_steps>=1"):
        _validate_sweep_config(**{**kwargs, "int_steps": 0}, source="test")
    for bad_dt in (np.inf, 0.0, -0.1):
        with pytest.raises(ValueError, match="dt>0"):
            _validate_sweep_config(**{**kwargs, "dt": bad_dt}, source="test")


def _result(
    *,
    amplitude: NDArray[np.float64] | None = None,
    es_proximity: float = 0.5,
    mu_raw: NDArray[np.float64] | None = None,
    mu_clamped: NDArray[np.float64] | None = None,
    mu_was_clipped: NDArray[np.bool_] | None = None,
    mu_clip_count: int = 0,
    mu_clip_mass: float = 0.0,
) -> StuartLandauResult:
    base_amp = np.array([1.0, 0.5], dtype=np.float64)
    base_mu = np.array([0.1, 0.2], dtype=np.float64)
    base_mask = np.array([False, False], dtype=np.bool_)
    return StuartLandauResult(
        amplitude=base_amp if amplitude is None else amplitude,
        phase=np.zeros(2, dtype=np.float64),
        order_parameter=0.5,
        hysteresis_area=0.1,
        es_proximity=es_proximity,
        leads_r_peak=False,
        mu_raw=base_mu if mu_raw is None else mu_raw,
        mu_clamped=base_mu.copy() if mu_clamped is None else mu_clamped,
        mu_was_clipped=base_mask if mu_was_clipped is None else mu_was_clipped,
        mu_clip_count=mu_clip_count,
        mu_clip_mass=mu_clip_mass,
    )


def test_result_audit_rejects_bounds_and_mu_inconsistency() -> None:
    """Result audit branches are non-decorative invariants."""
    _result()
    with pytest.raises(ValueError, match="amplitude below floor"):
        _result(amplitude=np.array([-1.0, 0.5], dtype=np.float64))
    for bad_es in (-0.1, 1.1):
        with pytest.raises(ValueError, match="es_proximity outside"):
            _result(es_proximity=bad_es)
    with pytest.raises(ValueError, match="raw/clamped shape mismatch"):
        _result(mu_clamped=np.array([0.1], dtype=np.float64))
    with pytest.raises(ValueError, match="clipped mask shape mismatch"):
        _result(mu_was_clipped=np.array([False], dtype=np.bool_))
    with pytest.raises(ValueError, match="clip count does not match"):
        _result(
            mu_was_clipped=np.array([True, False], dtype=np.bool_),
            mu_clip_count=0,
        )
    for bad_mass in (-0.1, np.inf):
        with pytest.raises(ValueError, match="clip mass"):
            _result(mu_clip_mass=bad_mass)


def test_z0_validation_rejects_shape_and_nonfinite_components() -> None:
    """Fitted-state validation must reject wrong shape and either non-finite axis."""
    good = np.array([1.0 + 0.0j, 0.5 + 0.25j], dtype=np.complex128)
    copied = _validate_z0(good, 2)
    assert copied.shape == (2,)
    assert copied.dtype == np.complex128
    assert copied is not good

    with pytest.raises(ValueError, match="z0 shape"):
        _validate_z0(good, 3)

    bad_real = np.array([np.nan + 0.0j, 1.0 + 0.0j], dtype=np.complex128)
    with pytest.raises(ValueError, match="z0 must be finite"):
        _validate_z0(bad_real, 2)

    bad_imag = np.array([complex(1.0, np.inf), 1.0 + 0.0j], dtype=np.complex128)
    with pytest.raises(ValueError, match="z0 must be finite"):
        _validate_z0(bad_imag, 2)


def test_hysteresis_sweep_uses_validated_external_z0() -> None:
    """External fitted state must enter the sweep through the same z0 guard."""
    mu = np.array([0.1, 0.2], dtype=np.float64)
    omega = np.array([0.3, 0.4], dtype=np.float64)
    bad_z0 = np.array([1.0 + 0.0j, np.nan + 0.0j], dtype=np.complex128)
    with pytest.raises(ValueError, match="z0 must be finite"):
        _hysteresis_sweep(
            mu,
            omega,
            K_low=0.0,
            K_high=1.0,
            K_steps=3,
            int_steps=2,
            dt=0.05,
            seed=0,
            z0=bad_z0,
        )


def _synthetic_prices(
    T: int = 64,
    N: int = 5,
    seed: int = 0,
    regime: str = "quiet",
) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    if regime == "quiet":
        rets = rng.standard_normal((T, N)) * 0.005
    elif regime == "crisis":
        common = np.cumsum(rng.standard_normal(T) * 0.01)
        common = common * np.linspace(0.5, 2.0, T)
        rets = (common[:, None] + 0.1 * rng.standard_normal((T, N))) * 0.01
    else:
        raise ValueError(f"unknown regime {regime!r}")
    prices: NDArray[np.float64] = (100.0 * np.exp(np.cumsum(rets, axis=0))).astype(
        np.float64
    )
    return prices


def test_amplitude_positive() -> None:
    """INV-SL1: amplitude ≥ 0 across many seeds (universal property)."""
    violations: list[tuple[int, float]] = []
    for seed in range(8):
        prices = _synthetic_prices(T=32, N=5, seed=seed)
        res = fit_stuart_landau(prices, K_steps=8, int_steps=80, seed=seed)
        amin = float(res.amplitude.min())
        if amin < 0.0:
            violations.append((seed, amin))
    assert isinstance(res, StuartLandauResult)
    assert res.amplitude.shape == (5,)
    assert not violations, (
        f"INV-SL1 VIOLATED: amplitude<0 in {len(violations)} of 8 seeds. "
        f"First: {violations[0] if violations else None}. "
        f"Stuart-Landau A=|z| must be non-negative by construction. "
        f"Tested over T=32, N=5, K_steps=8, int_steps=80."
    )


def test_es_proximity_bounded() -> None:
    """INV-SL2: es_proximity ∈ [0, 1] universally."""
    out_of_bounds: list[tuple[int, str, float]] = []
    for seed in range(8):
        for regime in ("quiet", "crisis"):
            prices = _synthetic_prices(T=32, N=5, seed=seed, regime=regime)
            res = fit_stuart_landau(prices, K_steps=8, int_steps=80, seed=seed)
            if not (0.0 <= res.es_proximity <= 1.0):
                out_of_bounds.append((seed, regime, res.es_proximity))
    assert not out_of_bounds, (
        f"INV-SL2 VIOLATED: es_proximity outside [0,1] in "
        f"{len(out_of_bounds)} cases of 16. "
        f"First violation: {out_of_bounds[0] if out_of_bounds else None}. "
        f"Tested over 8 seeds × 2 regimes (quiet, crisis). "
        f"K_steps=8, int_steps=80."
    )


def test_rolling_window_shape() -> None:
    """rolling_es_proximity output shape and NaN-prefix contract."""
    T, N, W = 48, 5, 16
    prices = _synthetic_prices(T=T, N=N, seed=0)
    out = rolling_es_proximity(prices, window=W, K_steps=6, int_steps=60)
    assert out.shape == (
        T,
    ), f"rolling shape mismatch: expected ({T},), got {out.shape}. window={W}."
    assert np.all(np.isnan(out[: W - 1])), (
        f"Pre-window indices [0,{W - 1}) must be NaN; "
        f"got finite at {np.where(np.isfinite(out[: W - 1]))[0]}."
    )
    valid = out[W - 1 :]
    assert np.any(
        np.isfinite(valid)
    ), "At least one rolling ES proximity value must be finite in [W-1, T)."


def test_crisis_signal_api() -> None:
    """API contract on crisis_signal_sl dict shape and types."""
    prices = _synthetic_prices(T=32, N=5, seed=0)
    sig = crisis_signal_sl(prices, K_steps=6, int_steps=60)
    required = {
        "es_proximity",
        "hysteresis_area",
        "order_parameter",
        "amplitude_max",
        "amplitude_min",
        "is_explosive",
        "leads_r_peak",
    }
    missing = required - sig.keys()
    assert not missing, f"crisis_signal_sl missing keys: {missing}"
    assert isinstance(sig["es_proximity"], float)
    assert isinstance(sig["is_explosive"], bool)
    assert isinstance(sig["leads_r_peak"], bool)
    es_val = sig["es_proximity"]
    assert isinstance(es_val, float) and 0.0 <= es_val <= 1.0
    op_val = sig["order_parameter"]
    assert isinstance(op_val, float) and 0.0 <= op_val <= 1.0
    amax = sig["amplitude_max"]
    amin = sig["amplitude_min"]
    assert isinstance(amax, float) and isinstance(amin, float)
    assert amax >= amin >= 0.0


def test_crisis_signal_uses_strict_es_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crisis boolean is strictly es_proximity > threshold, not >= or inverted."""

    def fake_fit_stuart_landau(
        *_args: object,
        **_kwargs: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            es_proximity=0.3,
            hysteresis_area=0.3,
            order_parameter=0.5,
            amplitude=np.array([1.0, 2.0], dtype=np.float64),
            leads_r_peak=False,
            mu_raw=np.array([0.1, 0.2], dtype=np.float64),
            mu_clamped=np.array([0.1, 0.2], dtype=np.float64),
            mu_was_clipped=np.array([False, False], dtype=np.bool_),
            mu_clip_count=0,
            mu_clip_mass=0.0,
        )

    monkeypatch.setattr(sl, "fit_stuart_landau", fake_fit_stuart_landau)
    prices = np.ones((8, 2), dtype=np.float64)
    at_threshold = sl.crisis_signal_sl(prices, es_threshold=0.3)
    below_threshold = sl.crisis_signal_sl(prices, es_threshold=0.31)
    above_threshold = sl.crisis_signal_sl(prices, es_threshold=0.29)
    assert at_threshold["is_explosive"] is False
    assert below_threshold["is_explosive"] is False
    assert above_threshold["is_explosive"] is True


def _rolling_R(prices: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Rolling Kuramoto order parameter via analytic phases."""
    T = prices.shape[0]
    out = np.full(T, np.nan, dtype=np.float64)
    log_prices = np.log(prices)
    for t in range(window, T):
        slab = np.diff(log_prices[t - window : t + 1], axis=0)
        centred = slab - slab.mean(axis=0)
        z = _analytic_signal(centred, axis=0)
        phase_last = np.angle(z[-1, :])
        out[t] = float(np.abs(np.mean(np.exp(1j * phase_last))))
    return out


def _smooth_box(x: NDArray[np.float64], width: int = 5) -> NDArray[np.float64]:
    out = np.full_like(x, np.nan)
    half = width // 2
    for i in range(len(x)):
        lo = max(0, i - half)
        hi = min(len(x), i + half + 1)
        seg = x[lo:hi]
        if np.any(np.isfinite(seg)):
            out[i] = float(np.nanmean(seg))
    return out


def test_leads_r_peak_on_synthetic_crisis() -> None:
    """INV-T2b: median ES peak precedes R peak across crisis seeds (smoothed)."""
    taus: list[int] = []
    T, N, W = 120, 6, 24
    for seed in range(8):
        rng = np.random.default_rng(seed)
        # construction: noise → ramp → peak → decay common factor
        factor = np.zeros(T, dtype=np.float64)
        factor[30:75] = np.linspace(0.0, 0.05, 45)
        factor[75:95] = 0.05
        factor[95:] = 0.05 * np.exp(-(np.arange(T - 95)) * 0.15)
        rets = factor[:, None] + rng.standard_normal((T, N)) * 0.003
        prices = 100.0 * np.exp(np.cumsum(rets, axis=0))

        es_raw = rolling_es_proximity(
            prices,
            window=W,
            K_steps=12,
            int_steps=120,
            seed=seed,
        )
        r_raw = _rolling_R(prices, window=W)
        if np.all(np.isnan(es_raw[W:])) or np.all(np.isnan(r_raw[W:])):
            continue
        es_smooth = _smooth_box(es_raw, width=5)
        r_smooth = _smooth_box(r_raw, width=5)
        es_peak = int(np.nanargmax(es_smooth))
        r_peak = int(np.nanargmax(r_smooth))
        taus.append(r_peak - es_peak)

    assert len(taus) >= 6, (
        f"INV-T2b test sample too small: {len(taus)} valid seeds of 8. "
        f"Synthetic crisis must yield finite rolling series; "
        f"check window/K_steps."
    )
    median_tau = float(np.median(taus))
    leads_count = sum(1 for t in taus if t >= 1)
    assert median_tau >= 1.0, (
        f"INV-T2b VIOLATED on synthetic crisis: median(τ)={median_tau} < 1. "
        f"Per-seed taus: {taus}. leads_count={leads_count}/{len(taus)}. "
        f"Construction: factor ramp t∈[30,75), peak [75,95), decay 95+. "
        f"T={T}, N={N}, W={W}, smoothing=box-5."
    )
    assert leads_count >= max(4, len(taus) // 2), (
        f"INV-T2b weak: only {leads_count}/{len(taus)} seeds had ES leading R. "
        f"Per-seed taus: {taus}."
    )


# ---------------------------------------------------------------------------
# Fail-closed contract guards (INV-SL contract / mu-audit).
#
# These tests pin the *disjunctive* structure of the fail-closed guards: each
# guard rejects an input when ANY one of two independent contract violations
# holds (logical OR). A blind spot would let a guard collapse to a conjunction
# (AND), silently admitting inputs that violate exactly one clause — the
# classic "boolop Or->And" mutation. Every assertion below isolates ONE clause
# so the guard must fire on it alone; an AND-collapsed guard would not raise
# and the test would fail. This is the falsification of the fail-closed promise,
# not a coverage decoration.
# ---------------------------------------------------------------------------


class _ResultKwargs(TypedDict):
    """Statically-typed constructor kwargs for ``StuartLandauResult``.

    Mirrors the dataclass fields exactly so ``StuartLandauResult(**kwargs)``
    type-checks under ``mypy --strict`` without an ``arg-type`` suppression,
    while individual fields can still be perturbed to runtime-invalid values.
    """

    amplitude: NDArray[np.float64]
    phase: NDArray[np.float64]
    order_parameter: float
    hysteresis_area: float
    es_proximity: float
    leads_r_peak: bool
    mu_raw: NDArray[np.float64]
    mu_clamped: NDArray[np.float64]
    mu_was_clipped: NDArray[np.bool_]
    mu_clip_count: int
    mu_clip_mass: float


def _valid_result_kwargs() -> _ResultKwargs:
    """Minimal kwargs that satisfy every StuartLandauResult.__post_init__ guard.

    Built so each individual field can be perturbed in isolation: amplitude ≥ 0,
    es_proximity ∈ [0, 1], raw/clamped/mask shapes agree, clip_count matches the
    mask, clip_mass finite and ≥ 0. Mutating exactly one field then probes the
    single guard responsible for it.
    """
    mu = np.array([0.1, 0.2], dtype=np.float64)
    mask = np.array([False, False], dtype=np.bool_)
    return {
        "amplitude": np.array([1.0, 2.0], dtype=np.float64),
        "phase": np.array([0.0, 0.0], dtype=np.float64),
        "order_parameter": 0.5,
        "hysteresis_area": 0.1,
        "es_proximity": 0.1,
        "leads_r_peak": False,
        "mu_raw": mu,
        "mu_clamped": mu.copy(),
        "mu_was_clipped": mask,
        "mu_clip_count": 0,
        "mu_clip_mass": 0.0,
    }


def test_valid_result_constructs() -> None:
    """Baseline: the canonical valid kwargs must construct without raising.

    Anchors the perturbation tests below — they are only meaningful if the
    unperturbed kwargs pass every __post_init__ guard.
    """
    res = StuartLandauResult(**_valid_result_kwargs())
    assert res.mu_clip_count == 0
    assert res.mu_clip_mass == 0.0


def test_mu_clip_mass_guard_rejects_nonfinite_or_negative() -> None:
    """INV-SL mu audit: clip mass must be finite AND ≥ 0 (disjunctive guard).

    The guard is ``mass < 0.0 OR not isfinite(mass)``. It must reject a value
    that violates EITHER clause alone: a finite-but-negative mass (clause 1
    only) and a non-negative-but-non-finite mass (clause 2 only, +inf and NaN).
    If the OR degenerated to AND, none of these single-clause violations would
    raise — clip mass is the integral of |mu_raw - mu_clamped|, so a negative or
    non-finite value is structurally impossible and must fail closed.
    """
    for bad_mass in (-1.0, np.inf, np.nan):
        kwargs = _valid_result_kwargs()
        kwargs["mu_clip_mass"] = float(bad_mass)
        with pytest.raises(ValueError, match="INV-SL mu audit VIOLATED: clip mass"):
            StuartLandauResult(**kwargs)


def test_sweep_config_rejects_nonfinite_K_either_endpoint() -> None:
    """INV-SL contract: finite K_low AND finite K_high required (disjunctive).

    Guard ``not isfinite(K_low) OR not isfinite(K_high)``. Isolate each endpoint:
    a non-finite K_high with finite K_low (clause 2 only) and a non-finite K_low
    with finite K_high (clause 1 only). An AND-collapsed guard would accept a
    sweep with exactly one infinite bound, which linspace would turn into an
    inf-laced K-grid and corrupt the integration silently.
    """
    with pytest.raises(ValueError, match="finite K_low/K_high required"):
        _validate_sweep_config(
            K_low=0.0, K_high=np.inf, K_steps=16, int_steps=200, dt=0.05, source="test"
        )
    with pytest.raises(ValueError, match="finite K_low/K_high required"):
        _validate_sweep_config(
            K_low=-np.inf, K_high=4.0, K_steps=16, int_steps=200, dt=0.05, source="test"
        )


def test_sweep_config_rejects_bad_K_steps() -> None:
    """INV-SL contract: K_steps must be an int AND ≥ 2 (disjunctive guard).

    Guard ``not isinstance(K_steps, int) OR K_steps < 2``. K_steps=1 is an int
    that violates only the magnitude clause; if the OR became AND it would pass
    (it IS an int), yielding a degenerate single-point sweep with no forward /
    backward branch and an undefined hysteresis area.
    """
    with pytest.raises(ValueError, match="integer K_steps>=2 required"):
        _validate_sweep_config(
            K_low=0.0, K_high=4.0, K_steps=1, int_steps=200, dt=0.05, source="test"
        )


def test_sweep_config_rejects_bad_int_steps() -> None:
    """INV-SL contract: int_steps must be an int AND ≥ 1 (disjunctive guard).

    Guard ``not isinstance(int_steps, int) OR int_steps < 1``. int_steps=0 is an
    int violating only the magnitude clause; under AND it would pass and the
    Euler integrator would take zero steps, leaving z at its initial state and
    fabricating a meaningless order parameter.
    """
    with pytest.raises(ValueError, match="integer int_steps>=1 required"):
        _validate_sweep_config(
            K_low=0.0, K_high=4.0, K_steps=16, int_steps=0, dt=0.05, source="test"
        )


def test_sweep_config_rejects_nonpositive_or_nonfinite_dt() -> None:
    """INV-SL contract: dt must be finite AND > 0 (disjunctive guard).

    Guard ``not isfinite(dt) OR dt <= 0.0``. dt=-1.0 is finite but non-positive
    (clause 2 only); dt=+inf is positive but non-finite (clause 1 only). An
    AND-collapsed guard would admit either, and an explicit-Euler step with a
    non-positive or infinite dt is numerically meaningless — must fail closed.
    """
    for bad_dt in (-1.0, np.inf):
        with pytest.raises(ValueError, match="finite dt>0 required"):
            _validate_sweep_config(
                K_low=0.0,
                K_high=4.0,
                K_steps=16,
                int_steps=200,
                dt=float(bad_dt),
                source="test",
            )


def test_validate_z0_rejects_nonfinite_real_or_imag() -> None:
    """INV-SL contract: z0 finite in BOTH real and imaginary parts (disjunctive).

    Guard ``not all(isfinite(z0.real)) OR not all(isfinite(z0.imag))``. Isolate
    each part: a finite real with an infinite imaginary component (clause 2
    only) and an infinite real with a finite imaginary component (clause 1
    only). If the OR became AND, a fitted state with one non-finite quadrature
    would be accepted and the Stuart-Landau RHS would propagate NaN/Inf silently.
    """
    z_bad_imag = np.array([1.0 + np.inf * 1j], dtype=np.complex128)
    with pytest.raises(ValueError, match="z0 must be finite"):
        _validate_z0(z_bad_imag, 1)
    z_bad_real = np.array([np.inf + 1.0j], dtype=np.complex128)
    with pytest.raises(ValueError, match="z0 must be finite"):
        _validate_z0(z_bad_real, 1)


def test_is_explosive_strictly_above_threshold() -> None:
    """INV-SL2 alarm: is_explosive flags es_proximity STRICTLY ABOVE threshold.

    crisis_signal_sl reports ``is_explosive = es_proximity > es_threshold``. The
    direction is load-bearing: a strict-greater comparison flipped to
    less-than-or-equal would invert the alarm, calling quiet regimes explosive
    and vice-versa. Anchor both sides on the SAME measured es_proximity: a
    threshold just below it must flag explosive, a threshold just above it must
    not. The 0.05 offsets keep both comparisons strict (no boundary equality).
    """
    prices = _synthetic_prices(T=32, N=5, seed=0, regime="crisis")
    es = fit_stuart_landau(prices, K_steps=6, int_steps=60, seed=0).es_proximity
    below = crisis_signal_sl(
        prices, es_threshold=es - 0.05, K_steps=6, int_steps=60, seed=0
    )
    above = crisis_signal_sl(
        prices, es_threshold=es + 0.05, K_steps=6, int_steps=60, seed=0
    )
    assert below["is_explosive"] is True, (
        f"INV-SL2 alarm VIOLATED: es_proximity={es:.6f} above threshold "
        f"{es - 0.05:.6f} must flag is_explosive=True; "
        f"is_explosive = es_proximity > es_threshold (strict). Got "
        f"{below['is_explosive']!r}."
    )
    assert above["is_explosive"] is False, (
        f"INV-SL2 alarm VIOLATED: es_proximity={es:.6f} below threshold "
        f"{es + 0.05:.6f} must flag is_explosive=False; "
        f"is_explosive = es_proximity > es_threshold (strict). Got "
        f"{above['is_explosive']!r}."
    )


# ---------------------------------------------------------------------------
# Issue #1358 acceptance criteria: fitted-state sweep, visible μ clip, and
# fail-closed rolling evidence. These lock the claim boundary in place so a
# future edit cannot silently revert to a seed-driven sweep, a silent μ clamp,
# or a NaN-masking evidence path.
# ---------------------------------------------------------------------------


def test_fitted_state_distinguishes_sweep_from_amplitude_phase() -> None:
    """P0-2: the sweep is initialised from fitted analytic state, not the seed.

    Two windows with the SAME mu/omega but DIFFERENT fitted amplitude/phase must
    produce a distinguishable hysteresis area — amplitude dynamics are physical
    in the Stuart-Landau RHS (|z|^2 z nonlinearity), so ignoring z0 and starting
    from ``seed`` would collapse both windows onto one identical trajectory. If
    ``_hysteresis_sweep`` ever drops the ``z0`` argument and falls back to the
    seed path, area_a and area_b would coincide (seed-only) and this fails.
    """
    n = 4
    mu = np.full(n, 0.2, dtype=np.float64)
    omega = np.linspace(0.1, 0.4, n).astype(np.float64)

    def _area(z0: NDArray[np.complex128] | None) -> float:
        area, _, _ = _hysteresis_sweep(
            mu,
            omega,
            K_low=0.0,
            K_high=4.0,
            K_steps=16,
            int_steps=200,
            dt=0.05,
            seed=42,
            z0=z0,
        )
        return area

    # Same mu/omega, two genuinely different fitted analytic states.
    z_low = (np.full(n, 0.2) * np.exp(1j * np.linspace(0.0, 1.0, n))).astype(
        np.complex128
    )
    z_high = (np.full(n, 1.5) * np.exp(1j * np.linspace(0.0, 3.0, n))).astype(
        np.complex128
    )
    area_low = _area(z_low)
    area_high = _area(z_high)
    area_seed = _area(None)

    assert abs(area_low - area_high) > 1e-6, (
        "INV-SL fitted-state VIOLATED: same mu/omega with different fitted "
        f"amplitude/phase gave indistinguishable sweep area "
        f"({area_low:.6e} vs {area_high:.6e}). Amplitude dynamics are physical; "
        "z0 must drive the sweep, not the seed."
    )
    # The fitted paths must also differ from the seed-only fallback, proving the
    # default evidence path does NOT silently use the random seed state.
    assert abs(area_low - area_seed) > 1e-9 and abs(area_high - area_seed) > 1e-9, (
        "INV-SL fitted-state VIOLATED: fitted sweep collapsed onto the seed-only "
        f"path (low={area_low:.6e}, high={area_high:.6e}, seed={area_seed:.6e}). "
        "The fitted z0 path must not equal the seeded fallback."
    )


def test_pathological_mu_is_clipped_visibly_not_silently() -> None:
    """P0-3: an over-Euler-band growth rate is clipped through the audit surface.

    A steep amplitude envelope (raw slope ≈ 2 > the ±1 Euler clamp) must surface
    on the audit tuple: ``mu_was_clipped`` all True, ``mu_clip_count`` == N, and
    ``mu_clip_mass`` > 0 measuring the removed growth-rate mass. A benign
    envelope (slope 0.1) must leave the audit surface pristine. This forbids a
    silent clamp: the clip event is observable, so downstream code cannot read a
    clipped window as unmodified physical evidence.
    """
    n_t, n = 8, 3
    t = np.arange(n_t, dtype=np.float64)

    steep = np.tile(np.exp(2.0 * t)[:, None], (1, n))
    mu_raw, mu_clamped, mask, count, mass = _estimate_growth_rate_audit(steep)
    assert np.allclose(mu_raw, 2.0, atol=1e-6) and np.allclose(mu_clamped, 1.0), (
        "INV-SL mu audit VIOLATED: steep envelope should give raw≈2, clamped=1; "
        f"got raw={mu_raw}, clamped={mu_clamped}."
    )
    assert bool(np.all(mask)) and count == n and mass > 0.0, (
        "INV-SL mu audit VIOLATED: pathological μ was clamped SILENTLY — audit "
        f"surface did not flag it (mask={mask}, count={count}, mass={mass}). "
        "Clip must be visible: mu_was_clipped all True, count==N, mass>0."
    )

    benign = np.tile(np.exp(0.1 * t)[:, None], (1, n))
    _, _, mask0, count0, mass0 = _estimate_growth_rate_audit(benign)
    assert not bool(np.any(mask0)) and count0 == 0 and mass0 == 0.0, (
        "INV-SL mu audit VIOLATED: benign envelope must not report any clip "
        f"(mask={mask0}, count={count0}, mass={mass0})."
    )


def test_rolling_es_proximity_fail_closed_raises_with_window_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1-1: evidence-mode rolling is fail-closed, not NaN-masking.

    When a window fit fails, ``fail_closed=False`` (exploratory) writes NaN, but
    ``fail_closed=True`` (evidence) must RAISE with the offending window index
    and the underlying cause, so physics-evidence generation cannot silently
    drop failed windows. A monkeypatched fit forces a deterministic failure at
    one window endpoint (returning a valid stub elsewhere); the two modes are
    asserted to diverge exactly there.
    """
    prices = _synthetic_prices(T=48, N=4, seed=0)
    window, fail_at = 16, 20
    target_last = float(prices[fail_at, 0])

    def _failing_fit(slab: NDArray[np.float64], **kwargs: object) -> StuartLandauResult:
        if slab.shape[0] == window and abs(float(slab[-1, 0]) - target_last) < 1e-12:
            raise ValueError("synthetic degenerate window for fail-closed probe")
        return _result(es_proximity=0.5)

    monkeypatch.setattr(sl, "fit_stuart_landau", _failing_fit)

    lenient = rolling_es_proximity(prices, window=window, step=1, fail_closed=False)
    assert np.isnan(lenient[fail_at]), (
        "INV-SL rolling VIOLATED: lenient mode must write NaN at the failed "
        f"window {fail_at}, got {lenient[fail_at]!r}."
    )
    with pytest.raises(RuntimeError, match="fail-closed") as excinfo:
        rolling_es_proximity(prices, window=window, step=1, fail_closed=True)
    message = str(excinfo.value)
    assert f"window_end={fail_at}" in message, (
        "INV-SL rolling fail-closed VIOLATED: raised error must name the "
        f"offending window index; got {message!r}."
    )
    assert "synthetic degenerate window" in message, (
        "INV-SL rolling fail-closed VIOLATED: raised error must carry the "
        f"underlying cause; got {message!r}."
    )


# ---------------------------------------------------------------------------
# PR #1425 strict-evidence binding: public-runtime-path regression guards.
#
# The prior P0-2/P0-3 acceptance tests exercise the *private* helpers
# (_hysteresis_sweep with an explicit z0, _estimate_growth_rate_audit directly).
# They prove the helpers CAN carry fitted state / clip audit, but not that the
# public entrypoint fit_stuart_landau() actually wires them through. A future
# edit could drop `z0=fitted_z0` or detach the mu-audit fields from the result
# while every private-helper test still passes. These two tests close that gap
# on the public path.
# ---------------------------------------------------------------------------


def test_fit_stuart_landau_passes_fitted_z0_to_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-3 (public path): fit_stuart_landau seeds the sweep from fitted analytic state.

    Monkeypatch ``_hysteresis_sweep`` to capture the ``z0`` it is called with when
    ``fit_stuart_landau(prices)`` runs. The captured state must be the fitted
    analytic vector ``amplitude · e^{iφ}`` — NOT ``None`` (seed-only fallback) and
    NOT the random seed state. If a future edit removes ``z0=fitted_z0`` from
    fit_stuart_landau, ``captured["z0"]`` becomes ``None`` and this test fails.
    """
    prices = _synthetic_prices(T=32, N=5, seed=3, regime="crisis")
    n = prices.shape[1]
    captured: dict[str, NDArray[np.complex128] | None] = {}

    def _capturing_sweep(
        mu: NDArray[np.float64],
        omega: NDArray[np.float64],
        *,
        z0: NDArray[np.complex128] | None = None,
        K_steps: int = 16,
        **_kwargs: object,
    ) -> tuple[float, NDArray[np.float64], NDArray[np.float64]]:
        captured["z0"] = z0
        zeros = np.zeros(K_steps, dtype=np.float64)
        return 0.25, zeros, zeros

    monkeypatch.setattr(sl, "_hysteresis_sweep", _capturing_sweep)
    fit_stuart_landau(prices, K_steps=8, int_steps=80, seed=7)

    z0 = captured.get("z0")
    assert z0 is not None, (
        "INV-SL fitted-state VIOLATED: fit_stuart_landau called the sweep with "
        "z0=None — it reverted to the seed-only fallback path instead of the "
        "fitted analytic state."
    )
    assert z0.shape == (n,), f"z0 shape mismatch: expected ({n},), got {z0.shape}."
    assert np.iscomplexobj(z0), "fitted z0 must be complex analytic state."
    assert np.all(np.isfinite(z0.real)) and np.all(np.isfinite(z0.imag)), (
        f"fitted z0 must be finite; got {z0!r}."
    )

    # It must equal the fitted analytic state amplitude·e^{iφ}, not the seed state.
    amplitude, phase, _omega, _mu = _extract_amplitude_phase_omega(prices)
    expected = (amplitude * np.exp(1j * phase)).astype(np.complex128)
    assert np.allclose(z0, expected), (
        "INV-SL fitted-state VIOLATED: fit_stuart_landau passed a z0 that is NOT "
        f"the fitted analytic state amplitude·e^(iφ). got={z0}, expected={expected}."
    )
    seed_state = _initial_state_from_seed(n, 7)
    assert not np.allclose(z0, seed_state), (
        "INV-SL fitted-state VIOLATED: the sweep z0 equals the random seed state — "
        "amplitude/phase information was discarded."
    )


def test_fit_stuart_landau_exposes_mu_clip_audit_on_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-4 (public path): the mu-clip audit surfaces on the StuartLandauResult.

    A benign panel leaves the audit pristine (clip_count == 0). Narrowing the
    Euler-stability band on the SAME public path (fit_stuart_landau → extract →
    _estimate_growth_rate_audit → clamp) forces a genuine clip whose evidence must
    appear on the returned result — mu_raw/mu_clamped finite, mu_was_clipped has a
    True, count == nonzero(mask), mass > 0. If the audit fields were removed,
    silently zeroed, or detached from the public result, this fails.
    """
    T, N = 40, 3
    rng = np.random.default_rng(0)
    t = np.arange(T - 1, dtype=np.float64)
    env = np.exp(0.06 * t)  # gentle, numerically stable growth → mu_raw ≈ 0.055
    log_rets = np.zeros((T - 1, N), dtype=np.float64)
    for j in range(N):
        log_rets[:, j] = 0.01 * env * np.sin(0.6 * t + j) + rng.standard_normal(T - 1) * 1e-6
    prices = np.empty((T, N), dtype=np.float64)
    prices[0, :] = 100.0
    prices[1:, :] = 100.0 * np.exp(np.cumsum(log_rets, axis=0))

    benign = fit_stuart_landau(prices, K_steps=8, int_steps=80, seed=0)
    assert benign.mu_clip_count == 0 and benign.mu_clip_mass == 0.0, (
        "INV-SL mu audit VIOLATED: benign panel must not report any clip on the "
        f"public result (count={benign.mu_clip_count}, mass={benign.mu_clip_mass})."
    )
    assert np.all(np.isfinite(benign.mu_raw)) and np.all(np.isfinite(benign.mu_clamped))

    # Narrow the ±clamp on the public path so the same panel clips for real.
    monkeypatch.setattr(sl, "_MU_GROWTH_CLAMP", 0.02)
    clipped = fit_stuart_landau(prices, K_steps=8, int_steps=80, seed=0)

    assert np.all(np.isfinite(clipped.mu_raw)) and np.all(np.isfinite(clipped.mu_clamped))
    assert bool(np.any(clipped.mu_was_clipped)), (
        "INV-SL mu audit VIOLATED: forced clip did not surface on the public "
        f"result mask (mu_was_clipped={clipped.mu_was_clipped})."
    )
    assert clipped.mu_clip_count == int(np.count_nonzero(clipped.mu_was_clipped)), (
        "INV-SL mu audit VIOLATED: public result clip_count detached from mask "
        f"(count={clipped.mu_clip_count}, mask={clipped.mu_was_clipped})."
    )
    assert clipped.mu_clip_mass > 0.0, (
        "INV-SL mu audit VIOLATED: forced clip reported zero mass on the public "
        f"result (mass={clipped.mu_clip_mass})."
    )
    assert np.isclose(
        clipped.mu_clip_mass, float(np.abs(clipped.mu_raw - clipped.mu_clamped).sum())
    ), "INV-SL mu audit VIOLATED: clip_mass on the result is not Σ|raw−clamped|."


def test_crisis_signal_exposes_mu_clip_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """P1-3: crisis_signal_sl surfaces the mu-clip audit, not just es/amplitude.

    The compact runtime signal must not hide a clamped growth-rate estimate: a
    downstream consumer reading only crisis_signal_sl() has to be able to tell a
    clipped window from a clean one.
    """
    prices = _synthetic_prices(T=32, N=5, seed=0, regime="crisis")
    clean = crisis_signal_sl(prices, K_steps=6, int_steps=60, seed=0)
    for key in ("mu_clip_count", "mu_clip_mass", "mu_was_clipped_any"):
        assert key in clean, f"crisis_signal_sl missing audit key: {key}"
    assert clean["mu_clip_count"] == 0
    assert clean["mu_was_clipped_any"] is False

    monkeypatch.setattr(sl, "_MU_GROWTH_CLAMP", 1e-3)
    clipped = crisis_signal_sl(prices, K_steps=6, int_steps=60, seed=0)
    assert clipped["mu_was_clipped_any"] is True
    clip_count = clipped["mu_clip_count"]
    clip_mass = clipped["mu_clip_mass"]
    assert isinstance(clip_count, int) and clip_count > 0
    assert isinstance(clip_mass, float) and clip_mass > 0.0
