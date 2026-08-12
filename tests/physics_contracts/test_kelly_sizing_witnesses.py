# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the Kelly-sizing laws in the physics catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real code, deriving every tolerance from the law. Two
previously-unwitnessed laws gain witnesses:

* ``kelly.fraction_cap``          — the applied fraction never exceeds the
  configured cap (INV-KELLY2).
* ``kelly.log_growth_optimality`` — the Kelly fraction f* = μ/σ² maximises
  expected log-growth E[log(1+f·X)] (INV-KELLY3, Monte-Carlo).

Nothing here is a market claim. These are optimal-growth facts about the code.
"""

from __future__ import annotations

import numpy as np

from core.neuro.kuramoto_kelly import KuramotoKellyAdapter
from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law

KELLY_FLOOR = 0.1
KELLY_CEIL = 1.0
# Strict definitional cap — only numerical round-off is permitted.
CAP_EPS = 1e-12


@law("kelly.fraction_cap", n_price_series=30, base_fractions=(0.05, 0.2, 0.5, 1.0))
def test_kelly_applied_fraction_respects_cap() -> None:
    """INV-KELLY2: the coherence-adjusted fraction never exceeds the cap.

    f_applied = kelly_base · scale with scale ∈ [floor, ceil]; therefore the
    applied fraction is bounded above by kelly_base·ceil and below by
    kelly_base·floor for every order-parameter regime. The sweep mixes incoherent
    random-walk series (low order parameter → scale near floor) with coherent
    oscillatory series (high order parameter → scale near ceil) so the cap is
    genuinely approached from below, not asserted on a slice where scale never
    leaves the floor; a vacuity guard requires the observed scale to reach the
    upper half of [floor, ceil].
    """
    n_price_series = 30
    base_fractions = (0.05, 0.2, 0.5, 1.0)
    adapter = KuramotoKellyAdapter(NeuroSignalBus(), floor=KELLY_FLOOR, ceil=KELLY_CEIL)
    rng = np.random.default_rng(seed=0)
    times = np.arange(128)
    series = [
        100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=40)))
        for _ in range(n_price_series)
    ]
    series += [
        100.0 * np.exp(0.05 * np.sin(2.0 * np.pi * freq * times)) for freq in (0.05, 0.1, 0.2)
    ]
    worst_overshoot = -np.inf
    worst_undershoot = np.inf
    max_scale = 0.0
    for prices in series:
        for kelly_base in base_fractions:
            applied = adapter.compute_kelly_fraction(kelly_base, prices)
            worst_overshoot = max(worst_overshoot, applied - kelly_base * KELLY_CEIL)
            worst_undershoot = min(worst_undershoot, applied - kelly_base * KELLY_FLOOR)
            max_scale = max(max_scale, applied / kelly_base)
    assert worst_overshoot <= CAP_EPS, (
        "INV-KELLY2 violated: observed worst overshoot = "
        f"{worst_overshoot:.3e} must be ≤ {CAP_EPS:.0e} (applied ≤ kelly_base·ceil) "
        f"over n_price_series={n_price_series} with seed=0 and ceil={KELLY_CEIL}"
    )
    midpoint = KELLY_FLOOR + 0.5 * (KELLY_CEIL - KELLY_FLOOR)
    assert max_scale >= midpoint, (
        "INV-KELLY2 vacuity guard: observed max scale = "
        f"{max_scale:.3f} must reach ≥ {midpoint:.3f} (upper half of [floor, ceil]) "
        f"with seed=0 and ceil={KELLY_CEIL}; the cap must be approached, not asserted "
        "on an all-floor slice"
    )
    assert worst_undershoot >= -CAP_EPS, (
        "INV-KELLY2 violated: observed worst undershoot = "
        f"{worst_undershoot:.3e} must be ≥ −{CAP_EPS:.0e} (applied ≥ kelly_base·floor) "
        f"over n_price_series={n_price_series} with seed=0 and floor={KELLY_FLOOR}"
    )


@law("kelly.log_growth_optimality", n_samples=200_000, grid_points=201)
def test_kelly_fraction_maximizes_log_growth() -> None:
    """INV-KELLY3: f* = μ/σ² maximises expected log-growth (Monte-Carlo).

    For X ~ Uniform(μ−a, μ+a) the continuous-limit Kelly fraction is
    f* = μ/σ² = 3μ/a². The witness estimates E[log(1+f·X)] on a grid of f and
    requires the empirical arg-max to coincide with f* to within the grid + MC
    budget, and that no grid fraction beats f* by more than 3 standard errors.
    """
    mu = 0.01
    half_width = 0.3
    sigma_squared = (half_width * half_width) / 3.0
    f_star = mu / sigma_squared
    n_samples = 200_000
    grid_points = 201
    rng = np.random.default_rng(seed=2)
    returns = rng.uniform(mu - half_width, mu + half_width, size=n_samples)

    grid = np.linspace(0.0, 1.0, grid_points)
    growth = np.array([float(np.mean(np.log1p(f * returns))) for f in grid])
    empirical_argmax = float(grid[int(np.argmax(growth))])

    grid_step = 1.0 / (grid_points - 1)
    budget = 2.0 * grid_step
    assert abs(f_star - empirical_argmax) <= budget, (
        "INV-KELLY3 violated: theoretical f*=μ/σ² = "
        f"{f_star:.4f} differs from empirical arg-max {empirical_argmax:.4f} by "
        f"more than grid+MC budget {budget:.4f} with n_samples={n_samples} and seed=2"
    )

    f_star_growth = float(np.mean(np.log1p(f_star * returns)))
    standard_error = float(np.std(np.log1p(f_star * returns)) / np.sqrt(n_samples))
    assert float(growth.max()) - f_star_growth <= 3.0 * standard_error, (
        "INV-KELLY3 violated: observed best grid growth exceeds growth at f* by "
        f"{float(growth.max()) - f_star_growth:.3e} which is more than 3·SE = "
        f"{3.0 * standard_error:.3e} with n_samples={n_samples} and seed=2; "
        "f* must be optimal within Monte-Carlo error"
    )
