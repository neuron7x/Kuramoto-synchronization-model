# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial robustness battery for the Tsallis entropy S_q (INV-FE2).

Two jobs:

1. **Fail-closed on dirty data** — non-finite position weights must RAISE, never
   return a silent NaN; a materially negative S_q must RAISE (it is a theorem,
   per Tsallis 1988, that S_q ≥ 0 for q>1 on the simplex).

2. **q is not an overfit knob** — the entropic index q (the system uses values
   around the low-q regime, e.g. q≈1.02, up through q=1.5) is shown to drive a
   SMOOTH, MONOTONE, LIPSCHITZ-bounded response with no knife-edge or special
   tuning at any particular q. A quantity that depends fragilely on a fitted q
   would be an overfitting artefact; a quantity that varies smoothly and
   monotonically in q is a structural property of the distribution.

Math anchor: Tsallis (1988). S_q = (1 − Σ wᵢ^q)/(q−1) on the probability
simplex; S_q ≥ 0 for q>1, S_q → Shannon as q→1, and ∂S_q/∂q ≤ 0 (entropy is
non-increasing in q for a fixed distribution).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.free_energy_trading_gate import FreeEnergyTradingGate

# q grid spanning the operational low-q regime (incl. q≈1.02) up to the default.
_Q_GRID = [1.001, 1.02, 1.05, 1.1, 1.25, 1.5, 2.0, 3.0]


def _distributions() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(20260618)
    return {
        "uniform": np.ones(16),
        "concentrated": np.array([10.0, 0.1, 0.1, 0.1, 0.1]),
        "bimodal": np.concatenate([rng.normal(5.0, 0.2, 8), rng.normal(0.05, 0.01, 8)]),
        "dirichlet": rng.dirichlet(np.ones(16)),
        "exponential": rng.exponential(1.0, 32),
    }


# ---------------------------------------------------------------------------
# 1. Validity: S_q ≥ 0 and finite for every q and every distribution.
# ---------------------------------------------------------------------------


def test_sq_nonnegative_finite_across_q_and_distributions() -> None:
    for name, w in _distributions().items():
        for q in _Q_GRID:
            gate = FreeEnergyTradingGate(q=q)
            s = gate.tsallis_entropy(w)
            assert np.isfinite(s), f"S_q non-finite for {name} at q={q}"
            assert s >= 0.0, f"INV-FE2: S_q={s} < 0 for {name} at q={q}"


# ---------------------------------------------------------------------------
# 2a. q is not overfit: S_q is MONOTONE non-increasing in q (theorem),
# so no distribution has a fragile peak at any particular q (e.g. 1.02).
# ---------------------------------------------------------------------------


def test_sq_monotone_nonincreasing_in_q() -> None:
    for name, w in _distributions().items():
        vals = [FreeEnergyTradingGate(q=q).tsallis_entropy(w) for q in _Q_GRID]
        diffs = np.diff(vals)
        assert np.all(diffs <= 1e-9), (
            f"INV-FE2: S_q must be non-increasing in q for {name}; got {vals}"
        )


# ---------------------------------------------------------------------------
# 2b. q is not overfit: the response is SMOOTH (no knife-edge) around q≈1.02 —
# the local finite-difference second derivative stays bounded, so q=1.02 is not
# a special/fragile operating point.
# ---------------------------------------------------------------------------


def test_sq_smooth_no_knife_edge_near_q_1p02() -> None:
    qs = np.linspace(1.005, 1.10, 40)
    w = _distributions()["bimodal"]
    vals = np.array([FreeEnergyTradingGate(q=float(q)).tsallis_entropy(w) for q in qs])
    # First differences are all finite and of one sign (monotone) — no jump.
    d1 = np.diff(vals)
    assert np.all(np.isfinite(d1))
    assert np.all(d1 <= 1e-12), "S_q not monotone — a jump implies a knife-edge"
    # Curvature (|second difference|) is bounded: no spike singling out q=1.02.
    d2 = np.abs(np.diff(d1))
    assert float(np.max(d2)) < 1e-2, f"curvature spike near q≈1.02: max|d2|={np.max(d2):.3e}"


# ---------------------------------------------------------------------------
# 2c. q is not overfit: SENSITIVITY is bounded — a ±10% perturbation of q
# changes S_q by a comparably small relative amount (Lipschitz, not knife-edge).
# An overfit knob would show a large response to a small q change.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("q0", [1.02, 1.1, 1.5])
def test_sq_sensitivity_to_q_is_bounded(q0: float) -> None:
    # The Tsallis deformation is parameterised by (q-1); perturb THAT by ±10%
    # (this stays in the valid q>1 domain even for q0≈1.02 and is the
    # physically meaningful sensitivity knob).
    w = _distributions()["bimodal"]
    d0 = q0 - 1.0
    base = FreeEnergyTradingGate(q=q0).tsallis_entropy(w)
    lo = FreeEnergyTradingGate(q=1.0 + d0 * 0.9).tsallis_entropy(w)
    hi = FreeEnergyTradingGate(q=1.0 + d0 * 1.1).tsallis_entropy(w)
    # Relative response to a ±10% move in (q-1) stays O(10%) — bounded
    # amplification, i.e. q is not a knife-edge overfit knob.
    rel = max(abs(hi - base), abs(lo - base)) / max(base, 1e-9)
    assert rel < 0.5, f"S_q over-sensitive to (q-1) at q0={q0}: rel-change {rel:.2f}"


# ---------------------------------------------------------------------------
# 3. Fail-closed on dirty data: non-finite weights MUST raise, not return NaN.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirty",
    [
        np.array([1.0, np.nan, 1.0]),
        np.array([1.0, np.inf, 1.0]),
        np.array([np.nan, np.nan]),
        np.array([1.0, -np.inf, 2.0]),
    ],
)
def test_dirty_weights_fail_closed(dirty: np.ndarray) -> None:
    gate = FreeEnergyTradingGate(q=1.02)
    with pytest.raises(ValueError, match="INV-FE2"):
        gate.tsallis_entropy(dirty)


def test_silent_nan_is_not_returned() -> None:
    """A NaN weight previously slipped the `total < 1e-12` guard (NaN<x is False)
    and produced a silent NaN entropy. Prove that path now raises."""
    gate = FreeEnergyTradingGate(q=1.02)
    with pytest.raises(ValueError, match="INV-FE2"):
        gate.tsallis_entropy(np.array([np.nan, 0.0, 0.0]))


def test_q_at_construction_must_exceed_one() -> None:
    """q ≤ 1 sign-flips the (q−1) denominator; rejected fail-closed at build."""
    with pytest.raises(ValueError):
        FreeEnergyTradingGate(q=1.0)
    with pytest.raises(ValueError):
        FreeEnergyTradingGate(q=0.95)


# ---------------------------------------------------------------------------
# 4. Preserve the documented degenerate behaviour: zero position mass -> 0.
# ---------------------------------------------------------------------------


def test_zero_weights_return_zero() -> None:
    assert FreeEnergyTradingGate(q=1.02).tsallis_entropy(np.zeros(5)) == 0.0
