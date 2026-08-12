# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for kelly_optimal_fraction (INV-KELLY1 / INV-KELLY2 / INV-KELLY3).

Reuses the real continuous-return Kelly function
``analytics.math_trading.kelly_criterion.kelly_from_edge_variance`` — the formula
``f* = edge / variance`` (== mu / sigma^2) with a hard applied-fraction cap. The
formula is NOT reimplemented here; the witnesses only probe the existing engine.

  INV-KELLY1 (algebraic): f* = mu / sigma^2 (continuous small-edge limit).
  INV-KELLY2 (universal):  applied fraction <= configured cap.
  INV-KELLY3 (statistical): E[log(1+f* X)] >= E[log(1+f' X)] for all f'.

Source: Kelly 1956; Thorp 2006; analytics/math_trading/kelly_criterion.py.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance

# (mu, sigma) small-edge pairs; sigma^2 chosen so f* = mu/sigma^2 is O(1).
_SWEEP: tuple[tuple[float, float], ...] = (
    (0.0005, 0.02),
    (0.0010, 0.03),
    (0.0020, 0.05),
    (0.0008, 0.04),
    (0.0003, 0.01),
    (0.0015, 0.06),
)

# Cap large enough that the raw formula never binds it in the equality sweep
# (max f* in the sweep is 0.0003/1e-4 = 3.0).
_UNBOUND_CAP = 1.0e9


def _log_growth(fraction: float, samples: npt.NDArray[np.float64]) -> float:
    """Empirical expected log-growth E[log(1 + f * X)] for a return sample."""
    return float(np.mean(np.log1p(fraction * samples)))


def test_optimal_fraction_equals_mu_over_sigma_squared() -> None:
    """Positive witness: f* == mu/sigma^2 to machine tol; applied fraction <= cap.

    INV-KELLY1: the unconstrained full-Kelly fraction is the exact algebraic
    ratio mu/sigma^2. INV-KELLY2: under a binding cap the applied fraction never
    exceeds it. Both are checked across the same (mu, sigma) sweep.
    """
    worst_residual = 0.0
    worst_overshoot = 0.0
    binding_cap = 0.5  # < max f* (=3.0) so the cap genuinely binds for some pairs
    for mu, sigma in _SWEEP:
        sigma_squared = sigma * sigma
        theoretical = mu / sigma_squared

        # INV-KELLY1: full Kelly (fraction=1) with a non-binding cap == mu/sigma^2.
        f_star = kelly_from_edge_variance(
            mu, sigma_squared, fractional_kelly=1.0, max_fraction=_UNBOUND_CAP
        )
        worst_residual = max(worst_residual, abs(f_star - theoretical))

        # INV-KELLY2: with a binding cap the applied fraction stays <= cap.
        applied = kelly_from_edge_variance(
            mu, sigma_squared, fractional_kelly=1.0, max_fraction=binding_cap
        )
        worst_overshoot = max(worst_overshoot, applied - binding_cap)

    assert worst_residual <= 1e-12, (
        f"INV-KELLY1 VIOLATED: max |f* - mu/sigma^2| = {worst_residual:.3e} > 1e-12. "
        f"f* must equal the exact algebraic ratio mu/sigma^2 (small-edge limit). "
        f"Continuous-return log-optimal fraction. "
        f"Reused analytics.math_trading.kelly_criterion.kelly_from_edge_variance. "
        f"Kelly 1956; Thorp 2006; sweep n={len(_SWEEP)}"
    )
    assert worst_overshoot <= 0.0, (
        f"INV-KELLY2 VIOLATED: applied fraction exceeded cap by {worst_overshoot:.3e}. "
        f"Applied fraction must satisfy applied <= configured cap. "
        f"Risk-policy clamp (max_fraction). "
        f"Reused kelly_from_edge_variance with max_fraction={binding_cap}. "
        f"Kelly 1956; sweep n={len(_SWEEP)}"
    )


def test_overbet_is_capped_and_degenerate_input_fails_closed() -> None:
    """Negative control: over-betting cannot bypass the cap; bad input fails closed.

    INV-KELLY2: a raw fraction far above the cap is clamped to the cap, never
    smuggled through. Degenerate inputs (zero/negative/NaN variance, non-finite
    edge) never yield an over-bet — they fail closed to 0.0 or are clamped to the
    cap. INV-KELLY3: a seeded log-growth check corroborates that f* is the
    maximiser (off-Kelly fractions grow strictly slower).
    """
    cap = 1.0

    # INV-KELLY2: raw f* = 0.5/0.01 = 50 >> cap; must be clamped to the cap.
    raw = 0.5 / 0.01
    over = kelly_from_edge_variance(0.5, 0.01, fractional_kelly=1.0, max_fraction=cap)
    assert over <= cap and over != raw, (
        f"INV-KELLY2 VIOLATED: over-bet {raw:.1f} smuggled past cap (got {over:.6f}). "
        f"An applied fraction above the cap must be clamped to the cap, not returned. "
        f"Risk-policy clamp on max_fraction. "
        f"Reused kelly_from_edge_variance(0.5, 0.01, max_fraction={cap}). "
        f"Kelly 1956; Thorp 2006"
    )

    # Degenerate / non-finite inputs must fail closed: result is finite, never
    # exceeds the cap, and zero-edge-information inputs return exactly 0.0.
    zero_cases: tuple[tuple[float, float], ...] = (
        (0.001, 0.0),  # zero variance -> no defined fraction
        (0.001, -1.0),  # negative variance is non-physical
        (float("nan"), 1.0),  # NaN edge
        (float("-inf"), 1.0),  # -inf edge (would imply infinite short)
        (0.001, float("nan")),  # NaN variance
        (-0.01, 0.04),  # negative edge -> no long position
    )
    for edge, variance in zero_cases:
        result = kelly_from_edge_variance(edge, variance, fractional_kelly=1.0, max_fraction=cap)
        assert np.isfinite(result) and result == 0.0, (
            f"INV-KELLY2 VIOLATED: degenerate input (edge={edge}, var={variance}) did not "
            f"fail closed (got {result}). "
            f"Zero/negative/NaN variance and non-positive/NaN edge must return 0.0. "
            f"Fail-closed contract on Kelly sizing. "
            f"Reused kelly_from_edge_variance; cap={cap}. Kelly 1956"
        )
    # A non-finite POSITIVE edge cannot produce an unbounded bet: it is clamped.
    inf_edge = kelly_from_edge_variance(float("inf"), 1.0, fractional_kelly=1.0, max_fraction=cap)
    assert np.isfinite(inf_edge) and inf_edge <= cap, (
        f"INV-KELLY2 VIOLATED: +inf edge produced an unbounded/over-cap fraction "
        f"(got {inf_edge}). Must be clamped to cap={cap}. "
        f"Fail-closed contract. Reused kelly_from_edge_variance. Kelly 1956"
    )

    # INV-KELLY3: log-growth optimality on a seeded Uniform(mu-a, mu+a) sample.
    # sigma^2 = a^2/3, so f* = mu/sigma^2 = 3*mu/a^2 (here = 1/3).
    rng = np.random.default_rng(7)
    mu, a, n = 0.01, 0.3, 2_000_000
    samples = rng.uniform(mu - a, mu + a, size=n)
    sigma_squared = a * a / 3.0
    f_star = kelly_from_edge_variance(
        mu, sigma_squared, fractional_kelly=1.0, max_fraction=_UNBOUND_CAP
    )
    g_star = _log_growth(f_star, samples)
    for multiplier in (0.5, 1.5, 2.0):
        g_off = _log_growth(multiplier * f_star, samples)
        assert g_star >= g_off, (
            f"INV-KELLY3 VIOLATED: off-Kelly fraction {multiplier}*f* grew faster "
            f"(g_off={g_off:.6e} > g*={g_star:.6e}). "
            f"E[log(1+f X)] must be maximised at f* = mu/sigma^2. "
            f"Seeded Uniform({mu - a},{mu + a}), n={n}. "
            f"f*={f_star:.6f} (= 3*mu/a^2). Kelly 1956; Thorp 2006"
        )
