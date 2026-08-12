# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed invariant tests for the Kuramoto order parameter (INV-K1).

INV-K1 is the Cauchy–Schwarz bound on the Kuramoto order parameter::

    R = |⟨e^{iθ}⟩| = |mean(exp(iθ))| ∈ [0, 1],   R = 1  iff  all θ_i equal.

The previous implementation ``float(np.clip(np.abs(z), 0.0, 1.0))`` SILENTLY
repaired any out-of-range magnitude. A clip is mathematically invisible: an
``R`` of ``1e9`` (a diverged / non-finite integrator state) and a true ``R`` of
``1.0`` both collapse to ``1.0``, so a broken integrator would report a perfect
synchronisation plateau. These tests pin the fail-closed contract:

* the valid path is byte-for-byte unchanged (identical phases → exactly 1.0,
  uniform random → finite-size floor ``≈ 1/√N``);
* a magnitude that exceeds ``1 + tol`` (``tol = 1e-8``) — beyond any plausible
  floating-point round-off — MUST raise rather than be clipped;
* non-finite phases (NaN / ±Inf) MUST raise;
* a 1000-array property sweep keeps every valid ``R`` finite and inside
  ``[0, 1]``.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto import engine
from core.kuramoto.engine import _INV_K1_ROUNDOFF_TOL, _order_parameter


class TestValidPathUnchanged:
    """The valid-path numeric behaviour must not change."""

    def test_identical_phases_give_exactly_one(self) -> None:
        # R = 1 iff all phases equal (Cauchy–Schwarz equality case).
        for n in (1, 2, 7, 256):
            theta = np.full(n, 0.73, dtype=np.float64)
            assert _order_parameter(theta) == pytest.approx(1.0, abs=1e-12)

    def test_identical_nonzero_phase_offset(self) -> None:
        # Equality holds for any common phase, not just 0.
        theta = np.full(64, -2.4, dtype=np.float64)
        assert _order_parameter(theta) == pytest.approx(1.0, abs=1e-12)

    def test_uniform_random_sits_near_finite_size_floor(self) -> None:
        # Incoherent phases ⇒ R ≈ O(1/√N). Average over seeds to suppress the
        # per-draw fluctuation and assert the scaling, not a single sample.
        n = 4096
        rng = np.random.default_rng(20260618)
        samples = [
            _order_parameter(rng.uniform(-np.pi, np.pi, size=n).astype(np.float64))
            for _ in range(64)
        ]
        mean_r = float(np.mean(samples))
        floor = 1.0 / np.sqrt(n)
        # mean |R| for uniform phases scales as sqrt(pi)/2 / sqrt(N) ≈ 0.886/√N.
        assert 0.3 * floor < mean_r < 3.0 * floor
        assert all(0.0 <= r <= 1.0 for r in samples)

    def test_returns_plain_finite_float_in_range(self) -> None:
        theta = np.linspace(0.0, 1.0, 11, dtype=np.float64)
        r = _order_parameter(theta)
        assert isinstance(r, float)
        assert np.isfinite(r)
        assert 0.0 <= r <= 1.0


class TestFailClosed:
    """Out-of-contract inputs must raise, never be silently clipped."""

    def test_nan_phase_raises_value_error(self) -> None:
        theta = np.array([0.0, np.nan, 1.0], dtype=np.float64)
        with pytest.raises(ValueError, match="INV-K1"):
            _order_parameter(theta)

    def test_inf_phase_raises_value_error(self) -> None:
        theta = np.array([0.0, np.inf, 1.0], dtype=np.float64)
        with pytest.raises(ValueError, match="INV-K1"):
            _order_parameter(theta)

    def test_neg_inf_phase_raises_value_error(self) -> None:
        theta = np.array([0.0, -np.inf, 1.0], dtype=np.float64)
        with pytest.raises(ValueError, match="INV-K1"):
            _order_parameter(theta)

    def test_magnitude_above_tol_raises_not_clipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the complex mean to land well above 1 + tol by monkeypatching the
        # module-local np.exp so that mean(exp(iθ)) has magnitude ~1.5. A silent
        # clip would return 1.0; the fail-closed contract MUST raise instead.
        def fake_exp(arg: np.ndarray) -> np.ndarray:
            return np.full_like(np.asarray(arg, dtype=np.complex128), 1.5 + 0.0j)

        monkeypatch.setattr(engine.np, "exp", fake_exp)
        with pytest.raises(FloatingPointError, match="INV-K1"):
            _order_parameter(np.zeros(8, dtype=np.float64))

    def test_magnitude_just_above_tol_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Exactly tol beyond 1 is the boundary; (1 + 2·tol) must still raise.
        over = 1.0 + 2.0 * _INV_K1_ROUNDOFF_TOL

        def fake_exp(arg: np.ndarray) -> np.ndarray:
            return np.full_like(np.asarray(arg, dtype=np.complex128), over + 0.0j)

        monkeypatch.setattr(engine.np, "exp", fake_exp)
        with pytest.raises(FloatingPointError, match="INV-K1"):
            _order_parameter(np.zeros(4, dtype=np.float64))

    def test_roundoff_within_tol_is_clipped_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Genuine round-off (≤ 1 + tol) is repaired into [0,1], not raised:
        # this is the one and only sanctioned clip.
        within = 1.0 + _INV_K1_ROUNDOFF_TOL / 2.0

        def fake_exp(arg: np.ndarray) -> np.ndarray:
            return np.full_like(np.asarray(arg, dtype=np.complex128), within + 0.0j)

        monkeypatch.setattr(engine.np, "exp", fake_exp)
        r = _order_parameter(np.zeros(4, dtype=np.float64))
        assert r == 1.0


class TestPropertySweep:
    """1000 valid random phase arrays ⇒ every R finite and in [0, 1]."""

    def test_thousand_valid_arrays_stay_in_unit_interval(self) -> None:
        rng = np.random.default_rng(7)
        for _ in range(1000):
            n = int(rng.integers(1, 512))
            theta = rng.uniform(-10.0 * np.pi, 10.0 * np.pi, size=n).astype(np.float64)
            r = _order_parameter(theta)
            assert isinstance(r, float)
            assert np.isfinite(r)
            assert 0.0 <= r <= 1.0
