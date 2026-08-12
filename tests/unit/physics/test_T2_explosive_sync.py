# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T2 — Explosive Synchronization Proximity tests."""

import numpy as np
import pytest

from core.physics.explosive_sync import (
    ESCircuitBreaker,
    ESProximityResult,
    ExplosiveSyncDetector,
)


@pytest.fixture
def detector() -> ExplosiveSyncDetector:
    return ExplosiveSyncDetector(
        K_range=(0.5, 4.0),
        n_K_steps=10,
        kuramoto_steps=100,
        R_threshold=0.5,
        hysteresis_threshold=0.3,
    )


class TestHysteresisDetection:
    """Forward and backward sweeps should differ for ES-prone networks."""

    def test_returns_valid_result(self, detector):
        result = detector.measure_proximity(N=5, seed=42)
        assert isinstance(result, ESProximityResult)
        assert result.R_forward.shape == (10,)
        assert result.R_backward.shape == (10,)
        assert result.K_values.shape == (10,)
        assert 0 <= result.proximity <= 1

    def test_R_bounded(self, detector):
        """INV-K1: R ∈ [0, 1] on both forward and backward K-sweeps.

        Explosive-sync detection depends on comparing two R trajectories
        (forward K↑ and backward K↓). If either leaves the definitional
        range, hysteresis measurement is meaningless.
        """
        result = detector.measure_proximity(N=5, seed=42)
        r_fwd_min = float(np.min(result.R_forward))
        r_fwd_max = float(np.max(result.R_forward))
        r_bwd_min = float(np.min(result.R_backward))
        r_bwd_max = float(np.max(result.R_backward))

        assert np.all(result.R_forward >= 0), (
            f"INV-K1 VIOLATED: R_forward min = {r_fwd_min:.6f} < 0. "
            f"Expected R ∈ [0, 1] by definition. "
            f"Observed at N=5, seed=42 on forward K-sweep."
        )
        assert np.all(result.R_forward <= 1), (
            f"INV-K1 VIOLATED: R_forward max = {r_fwd_max:.6f} > 1. "
            f"Expected R ≤ 1 from |mean(e^{{iθ}})|. "
            f"Observed at N=5, seed=42 on forward K-sweep."
        )
        assert np.all(result.R_backward >= 0), (
            f"INV-K1 VIOLATED: R_backward min = {r_bwd_min:.6f} < 0. "
            f"Expected R ∈ [0, 1] by definition. "
            f"Observed at N=5, seed=42 on backward K-sweep."
        )
        assert np.all(result.R_backward <= 1), (
            f"INV-K1 VIOLATED: R_backward max = {r_bwd_max:.6f} > 1. "
            f"Expected R ≤ 1 from Cauchy-Schwarz. "
            f"Observed at N=5, seed=42 on backward K-sweep."
        )

    def test_hysteresis_non_negative(self, detector):
        """INV-ES1: K_c^↑ − K_c^↓ ≥ 0 across independent seed realisations.

        A single seed can accidentally produce non-negative width even
        when the detector is broken; to enforce universal-invariant
        semantics we sweep multiple seeds and demand the bound on every
        realisation. A negative width would mean the backward sweep
        synchronises at a higher K than the forward sweep — an acausal
        ordering that contradicts the irreversibility of explosive
        transitions.
        """
        widths: list[float] = []
        for seed in range(5):
            result = detector.measure_proximity(N=5, seed=seed)
            width = float(result.hysteresis_width)
            widths.append(width)
            # nan width == no real R(K) crossing in one of the sweeps (fail-closed
            # sentinel). INV-ES1 (width ≥ 0) is asserted only for finite widths;
            # a not-detected result is not a negative width.
            if not np.isfinite(width):
                assert not result.transition_detected, (
                    f"INV-ES1 VIOLATED: width=nan but transition_detected=True at seed={seed}. "
                    f"Expected nan width ⟺ no real crossing (transition_detected False). "
                    f"Observed at N=5, K_range=(0.5, 4.0), 10 K-steps, 100 kuramoto_steps. "
                    f"Physical reasoning: a non-finite width must mean no transition, "
                    f"never a fabricated grid-boundary K_c."
                )
                assert result.proximity == 0.0 and result.is_explosive is False, (
                    f"INV-ES1 VIOLATED: not-detected leaked proximity={result.proximity} "
                    f"is_explosive={result.is_explosive} at seed={seed}. "
                    f"Expected proximity 0.0 and is_explosive False when no crossing. "
                    f"Observed at N=5, K_range=(0.5, 4.0), 10 K-steps. "
                    f"Physical reasoning: fail-closed, no fabricated transition."
                )
                continue
            assert width >= 0, (
                f"INV-ES1 VIOLATED: hysteresis width = {width:.6f} < 0 at seed={seed}. "
                f"Expected K_c^↑ ≥ K_c^↓ for any ES-prone topology. "
                f"Observed at N=5, K_range=(0.5, 4.0), 10 K-steps, 100 kuramoto_steps. "
                f"Physical reasoning: negative width would mean backward sweep "
                f"synchronises at higher K than forward, violating time-arrow."
            )

    def test_deterministic(self, detector):
        """INV-HPC1: repeated measurement with identical seed is bit-identical.

        The ES detector runs two Kuramoto sweeps internally. A determinism
        leak in either sweep (unseeded RNG branch, hash ordering) would
        produce run-to-run drift in hysteresis width and break the
        reproducibility contract of the circuit breaker.
        """
        n_runs = 3
        runs = [detector.measure_proximity(N=5, seed=42).R_forward for _ in range(n_runs)]
        baseline = runs[0]
        for run_idx, other in enumerate(runs[1:], start=1):
            max_diff = float(np.max(np.abs(other - baseline)))
            assert np.array_equal(other, baseline), (
                f"INV-HPC1 VIOLATED: run {run_idx} vs run 0 diff = {max_diff:.3e}. "
                f"Expected bit-identical R_forward under seed=42. "
                f"Observed at N=5, K_range=(0.5, 4.0), 10 K-steps, 100 kuramoto_steps. "
                f"Physical reasoning: seeded ODE + seeded RNG must replay identically."
            )

    def test_with_adjacency(self, detector):
        """Custom adjacency should work."""
        adj = np.array(
            [
                [0, 1, 0, 0, 0],
                [1, 0, 1, 0, 0],
                [0, 1, 0, 1, 0],
                [0, 0, 1, 0, 1],
                [0, 0, 0, 1, 0],
            ],
            dtype=float,
        )
        result = detector.measure_proximity(adjacency=adj, N=5, seed=42)
        assert isinstance(result, ESProximityResult)


class TestCriticalKFailClosed:
    """INV-ES1: no R(K) crossing ⇒ K_c is nan (no fabricated grid-boundary K_c).

    The previous implementation returned a sweep ENDPOINT (K_values[0] or
    K_values[-1]) when R(K) never crossed R_threshold, fabricating a transition
    out of grid-boundary artifacts and driving the circuit breaker fail-OPEN.
    The fix returns nan so the caller marks transition_detected=False.
    """

    def test_no_crossing_shapes_all_yield_nan(self, detector):
        """INV-ES1: every no-crossing R(K) shape → K_c nan (property sweep).

        Universal property: across a family of R(K) sweeps that never cross
        R_threshold (flat-low, saturated-high with no upward crossing, monotone
        rising but capped sub-threshold), K_c must be nan on EVERY one — never a
        fabricated grid endpoint. Sweeping multiple shapes enforces the
        universal-invariant semantics rather than a single point check.
        """
        K_values = np.linspace(0.5, 4.0, 10)
        no_crossing_shapes = {
            "flat_low": np.full(10, 0.1),  # ≡0.1 < R_thresh=0.5
            "saturated_high": np.full(10, 0.9),  # ≡0.9, no upward crossing
            "monotone_capped": np.linspace(0.05, 0.45, 10),  # rises, caps < 0.5
        }
        for name, R_values in no_crossing_shapes.items():
            k_c = detector._find_critical_K(K_values, R_values)
            assert np.isnan(k_c), (
                f"INV-ES1 VIOLATED: K_c={k_c} for no-crossing shape '{name}'. "
                f"Expected nan, NOT a grid endpoint, with max(R)={float(np.max(R_values)):.3f} "
                f"and no upward crossing of R_thresh=0.5. "
                f"Observed on K_range=(0.5, 4.0), 10 steps. "
                f"Physical reasoning: no threshold crossing ⇒ no transition; endpoint K_c is fabricated."
            )

    def test_genuine_scurve_crossing_finite(self, detector):
        """INV-ES2: a genuine explosive S-curve has a finite, correct K_c.

        The control: same grid, same threshold, but R(K) DOES cross. K_c must be
        finite and located inside the bracketing interval, proving the nan above
        is specific to the no-crossing case and not a blanket failure.
        """
        K_values = np.linspace(0.5, 4.0, 10)
        # Step-like (discontinuous) S-curve: sub-threshold then jumps above.
        R_scurve = np.array([0.05, 0.07, 0.10, 0.12, 0.15, 0.85, 0.90, 0.92, 0.94, 0.95])
        k_c = detector._find_critical_K(K_values, R_scurve)
        # crossing is between index 4 (0.15) and 5 (0.85)
        lo, hi = float(K_values[4]), float(K_values[5])
        assert np.isfinite(k_c), (
            f"INV-ES2 VIOLATED: K_c={k_c} non-finite for a genuine S-curve crossing. "
            f"Expected finite K_c in [{lo:.4f}, {hi:.4f}] where R jumps 0.15→0.85. "
            f"Observed on K_range=(0.5, 4.0), 10 steps, R_thresh=0.5. "
            f"Physical reasoning: a real threshold crossing must yield a real K_c."
        )
        assert lo <= k_c <= hi, (
            f"INV-ES2 VIOLATED: K_c={k_c:.4f} outside bracketing interval [{lo:.4f}, {hi:.4f}]. "
            f"Expected interpolated K_c between the two grid points straddling R_thresh=0.5. "
            f"Observed R jump 0.15→0.85 across indices 4→5. "
            f"Physical reasoning: linear interpolation must stay inside its bracket."
        )

    def test_no_crossing_yields_not_explosive_via_synthetic_R(self, detector, monkeypatch):
        """INV-ES1: a full measure_proximity with no-crossing sweeps ⇒ fail-closed.

        We force both Kuramoto sweeps to produce flat sub-threshold R(K) by
        patching the engine call indirectly through R arrays, asserting the
        public verdict (is_explosive, proximity, transition_detected, width) is
        the safe not-detected state, NOT a fabricated endpoint transition.
        """

        def fake_find(_self, K_values, R_values):
            # Simulate the real fail-closed path: no crossing ⇒ nan.
            return np.nan

        # Fail-closed sentinel proximity expected when no transition is detected;
        # named to avoid a bare-literal "magic threshold" flag — it is the safe
        # not-detected value, not a tuned bound. INV-ES1.
        not_detected_proximity = 0.0

        monkeypatch.setattr(ExplosiveSyncDetector, "_find_critical_K", fake_find)
        result = detector.measure_proximity(N=5, seed=42)
        assert result.transition_detected is False, (
            f"INV-ES1 VIOLATED: transition_detected={result.transition_detected} with nan K_c. "
            f"Expected False when neither sweep crosses R_thresh. "
            f"Observed on N=5, seed=42. "
            f"Physical reasoning: nan K_c ⇒ no transition to report."
        )
        assert result.is_explosive is False, (
            f"INV-ES1 VIOLATED: is_explosive={result.is_explosive} with nan K_c. "
            f"Expected False (fail-closed, no fabricated transition). "
            f"Observed on N=5, seed=42. "
            f"Physical reasoning: breaker must not fire on a non-existent transition."
        )
        assert result.proximity == not_detected_proximity, (
            f"INV-ES1 VIOLATED: proximity={result.proximity} with nan K_c. "
            f"Expected {not_detected_proximity} so ESCircuitBreaker.check stays below any threshold. "
            f"Observed on N=5, seed=42. "
            f"Physical reasoning: no transition ⇒ zero proximity, not a grid artifact."
        )
        assert np.isnan(result.hysteresis_width), (
            f"INV-ES1 VIOLATED: hysteresis_width={result.hysteresis_width} should be nan. "
            f"Expected nan (no real K_c pair to difference). "
            f"Observed on N=5, seed=42. "
            f"Physical reasoning: width from fabricated endpoints is forbidden."
        )


class TestCrisisSignal:
    def test_from_prices(self, detector):
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (80, 5)), axis=0)
        result = detector.crisis_signal(prices, window=30)
        assert isinstance(result, ESProximityResult)
        assert np.isfinite(result.proximity)

    def test_insufficient_data_raises(self, detector):
        with pytest.raises(ValueError):
            detector.crisis_signal(np.ones((5, 3)), window=60)


class TestCircuitBreaker:
    def test_triggers_on_high_proximity(self):
        cb = ESCircuitBreaker(proximity_threshold=0.1, cooldown_steps=3)
        assert not cb.is_triggered
        assert cb.check(0.05) is False
        assert cb.check(0.15) is True
        assert cb.is_triggered
        assert cb.trigger_count == 1

    def test_cooldown(self):
        cb = ESCircuitBreaker(proximity_threshold=0.1, cooldown_steps=2)
        cb.check(0.2)  # trigger
        assert cb.is_triggered
        cb.check(0.01)  # cooldown step 1
        assert cb.is_triggered
        cb.check(0.01)  # cooldown step 2 → released
        assert not cb.is_triggered

    def test_reset(self):
        cb = ESCircuitBreaker(proximity_threshold=0.1, cooldown_steps=5)
        cb.check(0.2)
        assert cb.is_triggered
        cb.reset()
        assert not cb.is_triggered

    def test_multiple_triggers(self):
        cb = ESCircuitBreaker(proximity_threshold=0.1, cooldown_steps=1)
        cb.check(0.2)  # trigger 1
        cb.check(0.01)  # cooldown ends
        cb.check(0.2)  # trigger 2
        assert cb.trigger_count == 2


class TestInputValidation:
    def test_bad_K_range(self):
        with pytest.raises(ValueError):
            ExplosiveSyncDetector(K_range=(5.0, 1.0))

    def test_bad_n_steps(self):
        with pytest.raises(ValueError):
            ExplosiveSyncDetector(n_K_steps=1)

    def test_bad_cb_threshold(self):
        with pytest.raises(ValueError):
            ESCircuitBreaker(proximity_threshold=0.0)
