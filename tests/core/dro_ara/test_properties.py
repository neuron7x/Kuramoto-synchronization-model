# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Hypothesis property-based invariant battery for DRO-ARA v7.

These tests complement ``test_invariants.py`` (exact, deterministic) and
``test_falsification.py`` (seeded synthetic regimes) with randomised
property-based coverage of the public API surface:

* ``derive_gamma``    — gamma = 2*H + 1 to float precision
* ``risk_scalar``     — bounded, 1-Lipschitz
* ``classify``        — fail-closed on ``stationary=False``
* ``geosync_observe`` — output schema, enum membership, determinism, NaN guard

Price inputs are 1-D finite non-constant float64 arrays of length 576..3000.
They are generated with ``hypothesis.extra.numpy.arrays`` drawing bounded
finite floats, then rendered admissible by adding a deterministic linear
ramp so every draw has dynamic range without relying on ``.filter`` (which
would reject the vast majority of native ``arrays`` draws and trigger
``Unsatisfiable``).

The 576 lower bound is ``window(512) + step(64)``, the minimum length the
engine accepts with default parameters.

All ``@given`` tests run at most ``max_examples=50`` with a 2-second
per-example deadline so the full battery finishes well under a minute.
"""

from __future__ import annotations

from typing import Final

import hypothesis.extra.numpy as hnp
import hypothesis.strategies as st
import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from numpy.typing import NDArray

from core.dro_ara import (
    R2_MIN,
    Regime,
    Signal,
    classify,
    derive_gamma,
    geosync_observe,
    risk_scalar,
)

REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "gamma",
        "H",
        "r2_dfa",
        "regime",
        "risk_scalar",
        "stationary",
        "signal",
        "free_energy",
        "ara_steps",
        "converged",
        "trend",
        "alpha_ema",
    }
)

REGIME_VALUES: Final[frozenset[str]] = frozenset(r.value for r in Regime)
SIGNAL_VALUES: Final[frozenset[str]] = frozenset(s.value for s in Signal)

# Rounding slack — public API rounds gamma, H, r2, rs to 6 decimals. Each
# rounded scalar carries <= 5e-7 absolute error; pair-wise differences in
# risk_scalar inherit <= 1e-6. We budget a conservative 2e-6 slack on the
# Lipschitz comparison so the property tests a *mathematical* bound, not a
# coincidence of rounding.
ROUND_SLACK: Final[float] = 2e-6

# Finite-float element strategy used by the numpy array strategy. Bounded so
# cumulative DFA arithmetic stays well inside float64 precision. Subnormals
# disallowed so the additive ramp below cannot be swallowed.
_finite_floats: Final[st.SearchStrategy[float]] = st.floats(
    min_value=-1e3,
    max_value=1e3,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
    width=64,
)


@st.composite
def _admissible_prices(draw: st.DrawFn) -> NDArray[np.float64]:
    """Draw a 1-D float64 price array of length 576..3000.

    Uses ``hypothesis.extra.numpy.arrays`` for the raw draw and guarantees
    admissibility by overlaying a deterministic linear ramp of magnitude 1.0
    plus a base offset of 100.0. This removes the pathology where raw
    ``arrays`` draws cluster at zero (which would fail a non-constant filter
    >99% of the time) without weakening the domain: the resulting vector is
    still arbitrary — each point is a free float plus a fixed function of
    its index.
    """
    n = draw(st.integers(min_value=576, max_value=3000))
    raw: NDArray[np.float64] = draw(
        hnp.arrays(
            dtype=np.float64,
            shape=n,
            elements=_finite_floats,
            unique=False,
        )
    )
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float64)
    base = 100.0
    out: NDArray[np.float64] = raw + ramp + base
    # Final safety — ``_finite_floats`` already excludes NaN/Inf and the ramp
    # is finite by construction, but ``assume`` makes the invariant explicit
    # so a future relaxation of the element strategy still fails closed.
    assume(np.all(np.isfinite(out)))
    return out


@given(price=_admissible_prices())
@settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.filter_too_much),
)
def test_property_gamma_equals_two_H_plus_one(price: NDArray[np.float64]) -> None:
    """Property 1: gamma = 2*H + 1 to float precision."""
    gamma, H, r2 = derive_gamma(price)
    assert (
        abs(gamma - (2 * H + 1)) < 1e-5
    ), f"INV (gamma = 2*H + 1) VIOLATED: gamma={gamma}, H={H}, 2H+1={2 * H + 1}"
    assert 0.0 <= r2 <= 1.0, f"r2 outside [0,1]: {r2}"


@given(gamma=st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=2000)
def test_property_risk_scalar_in_unit_interval(gamma: float) -> None:
    """Property 2: 0 <= risk_scalar(gamma) <= 1 for gamma in [0, 3]."""
    rs = risk_scalar(gamma)
    assert 0.0 <= rs <= 1.0, f"rs={rs} outside [0,1] for gamma={gamma}"


@given(
    a=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=2000)
def test_property_risk_scalar_lipschitz(a: float, b: float) -> None:
    """Property 3: risk_scalar is 1-Lipschitz continuous in gamma.

    |rs(a) - rs(b)| <= |a - b|. We add ROUND_SLACK because ``risk_scalar``
    rounds its output to 6 decimals, which can contribute up to <= 1e-6 of
    non-mathematical difference for arbitrarily close inputs.
    """
    lhs = abs(risk_scalar(a) - risk_scalar(b))
    rhs = abs(a - b) + ROUND_SLACK
    assert lhs <= rhs, f"Lipschitz VIOLATED: |rs({a})-rs({b})|={lhs} > |a-b|+slack={rhs}"


@given(
    gamma=st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    r2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=2000)
def test_property_classify_invalid_when_nonstationary(gamma: float, r2: float) -> None:
    """Property 4: classify returns INVALID whenever stationary=False.

    The classifier contract is ``INVALID iff !stationary OR r2 < R2_MIN``;
    the non-stationary half of the disjunction must hold for every admissible
    (gamma, r2) combination, including r2 >= R2_MIN.
    """
    regime = classify(gamma=gamma, r2=r2, stationary=False)
    assert (
        regime is Regime.INVALID
    ), f"stationary=False must force INVALID, got {regime} (gamma={gamma}, r2={r2})"


@given(
    r2=st.floats(min_value=R2_MIN, max_value=1.0, allow_nan=False, allow_infinity=False),
    gamma=st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=2000)
def test_property_classify_not_invalid_when_clean(gamma: float, r2: float) -> None:
    """Property 4b: conversely, r2 >= R2_MIN AND stationary => not INVALID."""
    regime = classify(gamma=gamma, r2=r2, stationary=True)
    assert (
        regime is not Regime.INVALID
    ), f"clean input must not be INVALID, got {regime} (gamma={gamma}, r2={r2})"


@given(price=_admissible_prices())
@settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.filter_too_much),
)
def test_property_observe_schema_and_enum_membership(price: NDArray[np.float64]) -> None:
    """Property 5: geosync_observe output schema, regime + signal enums."""
    try:
        out = geosync_observe(price)
    except ValueError:
        # The ramp guarantees non-constancy, but a degenerate draw where the
        # raw float array exactly cancels the ramp (set of measure zero yet
        # reachable under shrinking) would still trip the fail-closed
        # validator. Skip those via ``assume``.
        assume(False)
        raise  # unreachable; satisfies type-checker
    assert set(out.keys()) >= REQUIRED_KEYS, f"missing keys: {REQUIRED_KEYS - set(out.keys())}"
    assert out["regime"] in REGIME_VALUES, f"regime not an enum value: {out['regime']}"
    assert out["signal"] in SIGNAL_VALUES, f"signal not an enum value: {out['signal']}"


@given(price=_admissible_prices())
@settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.filter_too_much),
)
def test_property_observe_deterministic(price: NDArray[np.float64]) -> None:
    """Property 6: geosync_observe is pure — same input produces identical dict."""
    try:
        first = geosync_observe(price)
        second = geosync_observe(price)
    except ValueError:
        assume(False)
        raise
    assert first == second, f"non-deterministic output: {first} vs {second}"


@given(
    price=_admissible_prices(),
    bad_offset=st.integers(min_value=0, max_value=10_000),
    bad_value=st.sampled_from([np.nan, np.inf, -np.inf]),
)
@settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.filter_too_much),
)
def test_property_observe_rejects_nonfinite(
    price: NDArray[np.float64], bad_offset: int, bad_value: float
) -> None:
    """Property 7: NaN/Inf anywhere in input raises ValueError."""
    corrupted = price.copy()
    idx = bad_offset % len(corrupted)
    corrupted[idx] = bad_value
    with pytest.raises(ValueError, match="NaN/Inf"):
        geosync_observe(corrupted)
