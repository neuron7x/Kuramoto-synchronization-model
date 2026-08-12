# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# mypy: ignore-errors
# CI lane: integration-sweep regressions run in the heavy_math lane.
"""Runtime debt regressions for issue #1358."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from core.physics.stuart_landau_es import (
    _estimate_growth_rate_audit,
    fit_stuart_landau,
    rolling_es_proximity,
)

pytestmark = pytest.mark.heavy_math


def _synthetic_prices(
    T: int = 40,
    N: int = 5,
    seed: int = 0,
) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal((T, N)) * 0.004
    cumulative = np.cumsum(rets, axis=0)
    prices: NDArray[np.float64] = (100.0 * np.exp(cumulative)).astype(
        np.float64
    )
    return prices


def test_fitted_state_sweep_is_seed_invariant() -> None:
    """Default sweep must use fitted z0=A*exp(i*theta), not random state."""
    prices = _synthetic_prices(T=44, N=5, seed=7)
    first = fit_stuart_landau(prices, K_steps=7, int_steps=50, seed=1)
    second = fit_stuart_landau(prices, K_steps=7, int_steps=50, seed=999)
    assert first.es_proximity == pytest.approx(
        second.es_proximity,
        abs=0.0,
        rel=0.0,
    )
    assert first.hysteresis_area == pytest.approx(
        second.hysteresis_area,
        abs=0.0,
        rel=0.0,
    )


def test_mu_clamp_audit_surface_is_visible() -> None:
    """Pathological mu is bounded but exposed as clipped evidence."""
    n_t, n_assets = 8, 3
    t = np.arange(n_t, dtype=np.float64)
    envelope = np.tile(np.exp(2.0 * t)[:, None], (1, n_assets))
    mu_raw, mu_clamped, clipped, count, mass = _estimate_growth_rate_audit(
        envelope
    )
    assert np.all(mu_raw > 1.0)
    assert np.allclose(mu_clamped, 1.0)
    assert np.all(clipped)
    assert count == n_assets
    assert mass > 0.0


def test_fit_result_exposes_mu_clamp_audit_fields() -> None:
    """Result carries mu audit arrays, so clipping is not hidden."""
    prices = _synthetic_prices(T=40, N=4, seed=4)
    res = fit_stuart_landau(prices, K_steps=6, int_steps=40)
    assert res.mu_raw.shape == res.mu_clamped.shape == res.mu_was_clipped.shape
    assert res.mu_clip_count == int(np.count_nonzero(res.mu_was_clipped))
    assert res.mu_clip_mass >= 0.0


def test_rolling_fail_closed_raises_with_window_index() -> None:
    """Evidence mode must raise instead of hiding failures as NaN."""
    prices = _synthetic_prices(T=32, N=5, seed=2)
    exploratory = rolling_es_proximity(
        prices,
        window=16,
        K_steps=6,
        int_steps=20,
        dt=-0.1,
    )
    assert np.all(np.isnan(exploratory[15:]))
    with pytest.raises(RuntimeError, match="window_end=15"):
        rolling_es_proximity(
            prices,
            window=16,
            K_steps=6,
            int_steps=20,
            dt=-0.1,
            fail_closed=True,
        )
