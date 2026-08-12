# SPDX-License-Identifier: MIT
"""DRO-ARA public-surface witnesses — INV-DRO1/3/4 at the observer boundary.

Mechanism
---------
``core.dro_ara.engine`` measures the statistical regime of a synthetic price
series: it estimates the Hurst exponent ``H`` from DFA-1 on log-returns,
derives ``gamma = 2*H + 1``, confirms stationarity via a lag-augmented ADF
test on the same log-return transform, and emits a deterministic regime +
risk scalar through a bounded ARA loop. The public entry points are
:func:`derive_gamma` (pure estimator), :class:`State` /
:meth:`State.from_window` (one-window observation), and
:func:`geosync_observe` (full windowed observation returning a verdict dict).

Formula
-------
* ``gamma = 2*H + 1``  (Hurst→spectral-exponent relation; both fields are
  returned by the *same* DFA estimator and must never decouple).
* ``rs = max(0, 1 - |gamma - 1|) ∈ [0, 1]``  (risk scalar).
* ``regime == INVALID  ⟺  (not stationary) ∨ (r2 < R2_MIN)``.

Validity
--------
Synthetic inputs only (random walks, fractional-flavoured walks, linear
trends). DFA needs ``window`` ≥ a few hundred samples for a clean log-log fit;
:func:`geosync_observe` requires ``len(price) ≥ window + step``. No empirical
market data is touched.

Falsifier
---------
* INV-DRO1: if the *public* ``gamma`` field and the *public* ``H`` field of
  ``geosync_observe`` / ``State`` violate ``|gamma - (2H+1)| < TOL`` the
  observer has decoupled the two estimates — fail.
* INV-DRO5 boundary: if :func:`geosync_observe` (whose guard is
  ``min_len = window + step``, distinct from ``derive_gamma``'s 64-sample
  floor) returns silently on NaN / Inf / constant / too-short / non-1-D
  input, the fail-closed contract is broken — fail.
* INV-DRO3: if ``classify`` promotes a non-stationary or low-R² window to a
  non-INVALID regime, the stationarity gate has been bypassed — fail.

NON-CLAIM
---------
This module is a **regime observer, not a predictor**. The ``stationary`` /
ADF field and the ``regime`` / ``signal`` fields are *descriptive observer
flags* over a statistic of the input series. They carry **no market-causality
or alpha claim** and confer no predictive authority. All inputs here are
**synthetic-only**; the tests assert that the observer never emits a forward
return, probability-of-profit, or any causal-prediction field.

This file deliberately does NOT duplicate:
* ``test_T_dro1_gamma_algebraic.py`` — γ=2H+1 on the *derive_gamma* surface.
* ``test_inv_dro2_risk_scalar.py``   — rs bounds/Lipschitz on the *pure fn*.
* ``test_inv_dro5_fail_closed.py``   — fail-closed on the *derive_gamma* guard.
It covers the *public observer boundary* (``geosync_observe`` /
``State.from_window`` / ``classify``) that those pure-function tests do not.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from core.dro_ara.engine import (
    R2_MIN,
    RS_LONG_THRESH,
    Regime,
    Signal,
    State,
    classify,
    geosync_observe,
)

# ---------------------------------------------------------------------------
# Tolerance derivation for the public γ = 2H + 1 witness.
#
# geosync_observe / State expose ``gamma = round(2*H_true + 1, 6)`` and
# ``H = round(H_true, 6)`` — both rounded independently to 6 decimals from the
# *same* internal H_true. The residual of the public-field identity is:
#
#   |gamma_out - (2*H_out + 1)|
#     ≤ |gamma_out - (2*H_true + 1)|            (round of γ:  ≤ 0.5e-6)
#       + |(2*H_true + 1) - (2*H_out + 1)|      (round of H ×2: ≤ 2·0.5e-6)
#     ≤ 0.5e-6 + 1.0e-6 = 1.5e-6.
#
# So the algebraic identity holds at the public surface to ≤ 1.5e-6, which is
# comfortably inside the INV-DRO1 spec ceiling of 1e-5. We assert against the
# *spec* ceiling (the contract) and keep 1.5e-6 as the documented headroom.
# This is a formula-derived bound from the 6-decimal rounding, not a magic
# number.
# ---------------------------------------------------------------------------
_GAMMA_H_SPEC_TOL: float = 1e-5  # INV-DRO1 contract ceiling
_GAMMA_H_ROUNDING_BOUND: float = 1.5e-6  # derived 6-decimal double-round residual

# Output keys that, if ever present, would promote the observer to a predictor.
# The observer must expose statistics of the *current* window only — never a
# forward return, a profit probability, or a causal/alpha field.
_FORBIDDEN_PREDICTION_KEYS: frozenset[str] = frozenset(
    {
        "forecast",
        "prediction",
        "predicted_return",
        "future_return",
        "expected_return",
        "alpha",
        "edge",
        "win_probability",
        "prob_profit",
        "profit",
        "pnl",
        "target_price",
        "price_target",
    }
)


def _synthetic_walk(seed: int, n: int, *, drift: float = 0.0, scale: float = 1.0) -> NDArray[np.float64]:
    """Deterministic synthetic price path (random walk + optional drift)."""
    rng = np.random.default_rng(seed=seed)
    increments = rng.standard_normal(n) * scale + drift
    # Offset to keep prices strictly positive (log transform domain).
    return np.cumsum(increments) + 1000.0


# ===========================================================================
# INV-DRO1 at the public observer surface (gamma vs H from the OUTPUT dict).
# ===========================================================================


@pytest.mark.parametrize("seed", [0, 3, 17, 256, 9001])
def test_inv_dro1_public_observe_gamma_equals_2h_plus_1(seed: int) -> None:
    """geosync_observe output: |gamma - (2*H + 1)| < spec tol.

    Distinct from test_T_dro1 (which calls derive_gamma directly): here the
    fields travel through State.from_window → the verdict dict, so this also
    catches a refactor that recomputes either field on the public path.
    """
    price = _synthetic_walk(seed, n=900)
    out = geosync_observe(price)
    gamma = out["gamma"]
    h_val = out["H"]
    assert isinstance(gamma, float) and isinstance(h_val, float)
    assert math.isfinite(gamma) and math.isfinite(h_val), (
        f"INV-DRO1 VIOLATED (seed={seed}): non-finite public fields "
        f"gamma={gamma!r}, H={h_val!r}."
    )
    residual = abs(gamma - (2.0 * h_val + 1.0))
    assert residual < _GAMMA_H_SPEC_TOL, (
        f"INV-DRO1 VIOLATED at public observer surface (seed={seed}): "
        f"|gamma - (2H+1)| = {residual:.3e} ≥ spec tol {_GAMMA_H_SPEC_TOL:.0e}. "
        f"gamma={gamma!r}, H={h_val!r}. The two fields decoupled on the "
        "geosync_observe path. Derived headroom from 6-decimal double-round "
        f"is {_GAMMA_H_ROUNDING_BOUND:.1e}."
    )
    # Tighter sanity: the residual should actually sit inside the derived
    # rounding bound, not merely the looser spec ceiling.
    assert residual <= _GAMMA_H_ROUNDING_BOUND, (
        f"INV-DRO1 residual {residual:.3e} exceeds the derived 6-decimal "
        f"double-round bound {_GAMMA_H_ROUNDING_BOUND:.1e} (seed={seed}); "
        "the identity holds but with unexpected slack — investigate rounding."
    )


@pytest.mark.parametrize("seed", [1, 5, 42, 777])
def test_inv_dro1_state_surface_gamma_equals_2h_plus_1(seed: int) -> None:
    """State.from_window: gamma and H satisfy the algebraic identity."""
    price = _synthetic_walk(seed, n=700)
    state = State.from_window(price[:600])
    residual = abs(state.gamma - (2.0 * state.H + 1.0))
    assert residual <= _GAMMA_H_ROUNDING_BOUND, (
        f"INV-DRO1 VIOLATED on State surface (seed={seed}): "
        f"|gamma - (2H+1)| = {residual:.3e} > derived bound "
        f"{_GAMMA_H_ROUNDING_BOUND:.1e}. gamma={state.gamma!r}, H={state.H!r}."
    )


# ===========================================================================
# INV-DRO5 boundary at the PUBLIC entry: geosync_observe guard is
# min_len = window + step (NOT the 64-floor of derive_gamma). Falsifier:
# degenerate input must raise, never coerce.
# ===========================================================================


def test_inv_dro5_observe_rejects_nan() -> None:
    price = _synthetic_walk(2, n=900)
    price[400] = np.nan
    with pytest.raises(ValueError, match="NaN/Inf"):
        geosync_observe(price)


def test_inv_dro5_observe_rejects_inf() -> None:
    price = _synthetic_walk(2, n=900)
    price[400] = np.inf
    with pytest.raises(ValueError, match="NaN/Inf"):
        geosync_observe(price)


def test_inv_dro5_observe_rejects_constant() -> None:
    price = np.full(900, 50.0, dtype=np.float64)
    with pytest.raises(ValueError, match="constant"):
        geosync_observe(price)


def test_inv_dro5_observe_rejects_too_short_for_window_step() -> None:
    """The public guard floor is window+step, strictly above derive_gamma's 64.

    A 100-sample series passes derive_gamma's 64-floor but must be rejected by
    geosync_observe because 100 < window(512) + step(64) = 576. This pins the
    *distinct* public-entry guard the derive_gamma tests cannot reach.
    """
    price = _synthetic_walk(2, n=100)
    with pytest.raises(ValueError, match=r"need ≥576"):
        geosync_observe(price)


def test_inv_dro5_observe_rejects_non_1d() -> None:
    price = _synthetic_walk(2, n=900).reshape(2, 450)
    with pytest.raises(ValueError, match="1-D"):
        geosync_observe(price)


def test_inv_dro5_observe_short_input_is_not_silently_coerced() -> None:
    """Falsifier: ensure the guard RAISES rather than padding/truncating.

    A silent-coercion regression would return a dict instead of raising. We
    assert no dict escapes for a sub-floor input.
    """
    price = _synthetic_walk(2, n=200)  # 200 < 576
    raised = False
    try:
        geosync_observe(price)
    except ValueError:
        raised = True
    assert raised, (
        "INV-DRO5 VIOLATED: geosync_observe silently accepted a 200-sample "
        "input below the window+step floor (576) instead of raising. "
        "Fail-closed contract broken — input was coerced, not rejected."
    )


# ===========================================================================
# rs (risk scalar) bound at the PUBLIC output (not the pure function).
# ===========================================================================


@pytest.mark.parametrize("seed", [0, 4, 11, 99, 1234])
def test_observe_risk_scalar_in_unit_interval(seed: int) -> None:
    """Public ``risk_scalar`` field ∈ [0, 1] across synthetic regimes."""
    price = _synthetic_walk(seed, n=1000, scale=float(1 + seed % 5))
    out = geosync_observe(price)
    rs = out["risk_scalar"]
    assert isinstance(rs, float)
    assert 0.0 <= rs <= 1.0, (
        f"risk_scalar bound VIOLATED (seed={seed}): rs={rs!r} ∉ [0, 1] at the "
        "public observer surface. The bounded clip in risk_scalar() or the "
        "INVALID-regime zeroing in geosync_observe has been corrupted."
    )


def test_observe_invalid_regime_forces_rs_zero() -> None:
    """When the verdict regime is INVALID, the public rs must be exactly 0.

    Boundary witness: the engine zeroes rs on INVALID (non-stationary or
    low-R² or circuit-breaker). We construct a near-constant micro-noise
    series whose DFA R² is poor / regime degenerate and assert the coupling.
    If the regime is INVALID, rs must be 0; otherwise rs stays in [0, 1].
    """
    rng = np.random.default_rng(seed=2024)
    # Tiny-amplitude jitter on a flat baseline → weak/degenerate DFA fit.
    price = 100.0 + rng.standard_normal(900) * 1e-9
    out = geosync_observe(price)
    rs = out["risk_scalar"]
    assert 0.0 <= rs <= 1.0
    if out["regime"] == Regime.INVALID.value:
        assert rs == 0.0, (
            f"INVALID-regime coupling VIOLATED: regime=INVALID but rs={rs!r} "
            "!= 0.0. The fail-closed zeroing of risk on INVALID was removed."
        )


# ===========================================================================
# INV-DRO3: stationarity / R² gate. classify is the pure decision surface.
# ===========================================================================


@pytest.mark.parametrize("gamma", [1.5, 2.0, 1.9])
def test_inv_dro3_non_stationary_is_invalid(gamma: float) -> None:
    """Not stationary ⟹ INVALID regardless of R² or gamma."""
    regime = classify(gamma=gamma, r2=0.99, stationary=False)
    assert regime is Regime.INVALID, (
        f"INV-DRO3 VIOLATED: classify(stationary=False) = {regime} != INVALID "
        f"(gamma={gamma}, r2=0.99). The ADF gate was bypassed."
    )


@pytest.mark.parametrize("r2", [0.0, 0.5, R2_MIN - 1e-6])
def test_inv_dro3_low_r2_is_invalid(r2: float) -> None:
    """R² below R2_MIN ⟹ INVALID even when stationary."""
    regime = classify(gamma=2.0, r2=r2, stationary=True)
    assert regime is Regime.INVALID, (
        f"INV-DRO3 VIOLATED: classify(r2={r2} < {R2_MIN}, stationary=True) = "
        f"{regime} != INVALID. The R² fit-quality gate was bypassed."
    )


def test_inv_dro3_stationary_and_good_fit_is_not_invalid() -> None:
    """Inverse boundary: stationary AND R² ≥ R2_MIN ⟹ NOT INVALID.

    Without this companion a regression that returns INVALID unconditionally
    would pass the rejection tests while breaking the admissible path.
    """
    regime = classify(gamma=1.8, r2=0.95, stationary=True)
    assert regime is not Regime.INVALID, (
        "INV-DRO3 inverse VIOLATED: a stationary, well-fit window "
        f"(r2=0.95 ≥ {R2_MIN}) was classified INVALID. The gate over-rejects."
    )


# ===========================================================================
# NON-CLAIM: stationarity / ADF is a DESCRIPTIVE OBSERVER FLAG, not a
# market-truth or prediction. The observer must not promote to alpha.
# ===========================================================================


@pytest.mark.parametrize("seed", [0, 13, 200])
def test_stationary_field_is_descriptive_boolean_observer_flag(seed: int) -> None:
    """``stationary`` is a plain bool observation, carrying no forward claim."""
    price = _synthetic_walk(seed, n=900)
    out = geosync_observe(price)
    stationary = out["stationary"]
    assert isinstance(stationary, bool), (
        f"NON-CLAIM VIOLATED: 'stationary' field is {type(stationary).__name__}, "
        "not a bool. An observer flag must stay a descriptive boolean, never a "
        "score that could be read as a confidence/probability of a market move."
    )


def test_observe_emits_no_prediction_or_alpha_field() -> None:
    """Falsifier for promotion-leakage: no forecast/alpha/profit key may appear.

    The observer reports statistics of the *current* window (gamma, H, r2,
    regime, signal, free_energy). It must NOT expose a forward return, a
    profit probability, or any causal/alpha field. If such a key ever appears
    the module has silently promoted itself from observer to predictor.
    """
    price = _synthetic_walk(5, n=1024)
    out = geosync_observe(price)
    leaked = _FORBIDDEN_PREDICTION_KEYS.intersection(out.keys())
    assert not leaked, (
        f"NON-CLAIM VIOLATED: geosync_observe leaked prediction/alpha keys "
        f"{sorted(leaked)}. This module is a regime OBSERVER, not a predictor; "
        "it must not emit forward-return or profitability claims."
    )


def test_signal_is_categorical_label_not_a_quantified_edge() -> None:
    """``signal`` is a categorical observer label, not a numeric alpha/edge.

    A categorical {LONG, SHORT, HOLD, REDUCE} label is a description of the
    observed regime; it is not a position size, expected return, or edge. We
    assert the field is one of the closed enum labels and never a number.
    """
    price = _synthetic_walk(8, n=1024)
    out = geosync_observe(price)
    signal = out["signal"]
    assert isinstance(signal, str) and not isinstance(signal, bool), (
        f"NON-CLAIM VIOLATED: 'signal' is {type(signal).__name__}; a numeric "
        "signal would read as a quantified edge/alpha. It must be a label."
    )
    assert signal in {s.value for s in Signal}, (
        f"NON-CLAIM VIOLATED: signal={signal!r} ∉ closed label set "
        f"{[s.value for s in Signal]}. An observer must emit only the declared "
        "categorical regime labels, never an open-ended quantified edge."
    )


def test_regime_is_closed_descriptive_label_set() -> None:
    """``regime`` ∈ the closed descriptive enum; no open-ended truth claim."""
    price = _synthetic_walk(21, n=1024)
    out = geosync_observe(price)
    regime = out["regime"]
    assert regime in {r.value for r in Regime}, (
        f"NON-CLAIM VIOLATED: regime={regime!r} ∉ {[r.value for r in Regime]}. "
        "The regime is a descriptive label over a statistic, not a market "
        "state-of-the-world truth claim."
    )


def test_long_signal_requires_critical_and_rs_above_threshold() -> None:
    """INV-DRO4 sanity at the boundary: LONG ⟹ CRITICAL ∧ rs > thresh.

    Not a duplicate of any existing test (DRO4 has no dedicated file). When a
    LONG label is emitted, the descriptive preconditions must hold — the label
    cannot be promoted ahead of its own gate.
    """
    for seed in range(40):
        price = _synthetic_walk(seed, n=1100)
        out = geosync_observe(price)
        if out["signal"] == Signal.LONG.value:
            assert out["regime"] == Regime.CRITICAL.value, (
                f"INV-DRO4 VIOLATED (seed={seed}): LONG with regime="
                f"{out['regime']} != CRITICAL."
            )
            assert out["risk_scalar"] > RS_LONG_THRESH, (
                f"INV-DRO4 VIOLATED (seed={seed}): LONG with rs="
                f"{out['risk_scalar']} ≤ {RS_LONG_THRESH}."
            )
            assert out["trend"] in ("CONVERGING", "STABLE"), (
                f"INV-DRO4 VIOLATED (seed={seed}): LONG with trend="
                f"{out['trend']} ∉ {{CONVERGING, STABLE}}."
            )
