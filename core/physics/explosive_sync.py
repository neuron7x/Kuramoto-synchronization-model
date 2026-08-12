# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T2 — Explosive Synchronization Proximity as Crisis Early-Warning.

Explosive synchronization (ES) = first-order (discontinuous) phase transition
in the order parameter R, as opposed to the smooth second-order transition
in classical Kuramoto.

Detection method (Lee et al. PNAS 2025 framework):
    1. Sweep coupling K from K_low to K_high (forward) and back (backward)
    2. Measure R(K) in both directions
    3. Hysteresis width = K_c_forward - K_c_backward
    4. ES proximity = hysteresis_width / K_range

Signal interpretation:
    R(t) ↑ + hysteresis_width ↑  =  pre-crisis (system near explosive transition)
    R(t) stable + width ≈ 0      =  normal (smooth transition)

Integration: circuit breaker in Risk Manager.
When ES proximity exceeds threshold → escalate FailSafe to RESTRICTED.

References:
    Gómez-Gardeñes et al. "Explosive synchronization transitions" PRL (2011)
    Lee, U. et al. (2025). "Proximity to explosive synchronization determines
        network collapse and recovery trajectories in neural and economic
        crises." PNAS 122(44). DOI: 10.1073/pnas.2505434122
    D'Souza et al. "Explosive phenomena in complex networks" Adv. Phys. (2019)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# Integration time-step handed to KuramotoConfig for every sweep. Kept as a
# named module constant (not a bare literal) because it is ALSO the unit-bridge
# denominator that converts a per-bar return into an angular frequency (see
# _RETURN_TO_OMEGA below). Changing one without the other would silently break
# the frequency normalization. The Kuramoto engine integrates phase as
# θ̇ = ω + coupling, so ω has units of [rad / integration-time-unit].
_INTEGRATION_DT: float = 0.01

# Unit bridge: a return r_t is a dimensionless change measured PER BAR. To enter
# the Kuramoto flow it must become an angular velocity ω in [rad / integration-
# time-unit]. One bar advances the integrator by _INTEGRATION_DT time-units, so
# the per-time-unit phase rate is r_t / _INTEGRATION_DT (= r_t · 100 at dt=0.01).
# This is the documented derivation of the former magic "* 100": it is exactly
# 1/dt, NOT a free tuning knob. It rescales O(1e-3..1e-2) bar returns onto the
# same O(1) scale as the reference N(0,1) natural frequencies so the coupling
# sweep K_range=(0.1, 5.0) brackets the transition.
# bounds: pure unit conversion (per-bar → per-integration-time-unit); no clamp.
_RETURN_TO_OMEGA: float = 1.0 / _INTEGRATION_DT


@dataclass(frozen=True, slots=True)
class ESProximityResult:
    """Result of explosive synchronization proximity measurement."""

    R_forward: NDArray[np.float64]  # R(K) forward sweep
    R_backward: NDArray[np.float64]  # R(K) backward sweep
    K_values: NDArray[np.float64]  # coupling values swept
    K_c_forward: float  # critical K (forward); nan if no R(K) crossing
    K_c_backward: float  # critical K (backward); nan if no R(K) crossing
    hysteresis_width: float  # loop width; exact if both K_c finite, else a
    # lower bound (K_c_forward - K_min) when the backward branch stays synced
    # below the grid (see hysteresis_is_lower_bound); nan if no real transition
    proximity: float  # normalised proximity metric [0, 1]; 0.0 when no transition
    is_explosive: bool  # True if significant hysteresis detected
    transition_detected: bool  # True iff a real forward transition was observed
    # (both branches cross, OR forward crosses and backward stays synchronized)
    hysteresis_is_lower_bound: bool = False  # True ⟹ width is a lower bound
    # (down-transition lies below K_min; grid cannot bracket it)


class ExplosiveSyncDetector:
    """Detect proximity to explosive (first-order) synchronization transition.

    Parameters
    ----------
    K_range : tuple[float, float]
        Range of coupling strengths to sweep (default (0.1, 5.0)).
    n_K_steps : int
        Number of coupling values in sweep (default 20).
    kuramoto_steps : int
        Integration steps per K value (default 300).
    R_threshold : float
        Order parameter threshold for "synchronized" (default 0.5).
    hysteresis_threshold : float
        Minimum hysteresis width to declare ES (default 0.3).
    """

    def __init__(
        self,
        K_range: tuple[float, float] = (0.1, 5.0),
        n_K_steps: int = 20,
        kuramoto_steps: int = 300,
        R_threshold: float = 0.5,
        hysteresis_threshold: float = 0.3,
    ) -> None:
        if K_range[0] >= K_range[1]:
            raise ValueError(f"K_range must be (low, high), got {K_range}")
        if n_K_steps < 2:
            raise ValueError(f"n_K_steps must be ≥ 2, got {n_K_steps}")
        self._K_range = K_range
        self._n_K = n_K_steps
        self._steps = kuramoto_steps
        self._R_thresh = R_threshold
        self._hyst_thresh = hysteresis_threshold

    def measure_proximity(
        self,
        adjacency: NDArray[np.float64] | None = None,
        omega: NDArray[np.float64] | None = None,
        N: int = 10,
        seed: int = 42,
    ) -> ESProximityResult:
        """Sweep K forward and backward, measure hysteresis.

        Parameters
        ----------
        adjacency : optional (N, N) adjacency matrix.
        omega : optional (N,) natural frequencies.
        N : int, number of oscillators if omega not given.
        seed : int, RNG seed for reproducibility.

        Returns
        -------
        ESProximityResult with hysteresis analysis.
        """
        from core.kuramoto.config import KuramotoConfig
        from core.kuramoto.engine import KuramotoEngine

        K_values = np.linspace(self._K_range[0], self._K_range[1], self._n_K)

        # Use consistent initial conditions for both sweeps
        rng = np.random.default_rng(seed)
        if omega is None:
            omega = rng.standard_normal(N)
        else:
            N = omega.shape[0]

        theta0_base = rng.uniform(0, 2 * np.pi, N)

        R_forward = np.zeros(self._n_K)
        R_backward = np.zeros(self._n_K)

        # Forward sweep: increasing K, carry final phases forward
        theta_carry = theta0_base.copy()
        for i, K in enumerate(K_values):
            cfg = KuramotoConfig(
                N=N,
                K=K,
                omega=omega,
                adjacency=adjacency,
                adjacency_kind="normalized_topology",
                theta0=theta_carry,
                dt=_INTEGRATION_DT,
                steps=self._steps,
                seed=seed,
            )
            result = KuramotoEngine(cfg).run()
            R_forward[i] = result.order_parameter[-1]
            theta_carry = result.phases[-1].copy()

        # Backward sweep: decreasing K, carry final phases backward
        theta_carry_back = theta_carry.copy()
        for i, K in enumerate(reversed(K_values)):
            cfg = KuramotoConfig(
                N=N,
                K=K,
                omega=omega,
                adjacency=adjacency,
                adjacency_kind="normalized_topology",
                theta0=theta_carry_back,
                dt=_INTEGRATION_DT,
                steps=self._steps,
                seed=seed,
            )
            result = KuramotoEngine(cfg).run()
            R_backward[self._n_K - 1 - i] = result.order_parameter[-1]
            theta_carry_back = result.phases[-1].copy()

        # Find critical K values. nan means "no real R(K) threshold crossing in
        # this sweep" — NOT a transition at a grid endpoint (see _find_critical_K).
        K_c_fwd = self._find_critical_K(K_values, R_forward)
        K_c_bwd = self._find_critical_K(K_values, R_backward)

        # Fail-closed: hysteresis is only meaningful when BOTH sweeps crossed the
        # synchronization threshold. If either K_c is nan, there is no real
        # transition to compare, so we do NOT fabricate a width from grid-boundary
        # artifacts. We propagate nan width, proximity 0.0, and is_explosive=False
        # so the circuit breaker treats it as "no transition detected" rather than
        # firing on a boundary value (fail-OPEN to RESTRICTED). INV-ES1 (width ≥ 0)
        # holds vacuously: a nan width is never reported as a negative number.
        K_min = float(K_values[0])
        hysteresis_is_lower_bound = False
        if math.isfinite(K_c_fwd) and math.isfinite(K_c_bwd):
            # Both branches cross on the grid → exact hysteresis loop width.
            hysteresis = abs(K_c_fwd - K_c_bwd)  # INV-ES1: |·| ⇒ width ≥ 0
            transition_detected = True
        elif math.isfinite(K_c_fwd) and float(R_backward[0]) >= self._R_thresh:
            # Strong hysteresis: the forward up-transition is at K_c_fwd, but the
            # backward branch is STILL synchronized at the grid floor (R_backward
            # at K_min ≥ threshold), so the down-transition lies BELOW K_min and
            # the grid cannot bracket it. This is genuine explosive evidence — the
            # loop is at least (K_c_fwd − K_min) wide. We report that honest LOWER
            # BOUND (flagged), NOT a fabricated grid-endpoint K_c: the down-branch
            # is observed synchronized, it is not a boundary artifact. INV-ES2.
            hysteresis = K_c_fwd - K_min  # INV-ES1: K_c_fwd ≥ K_min ⇒ width ≥ 0
            transition_detected = True
            hysteresis_is_lower_bound = True
        else:
            # No real transition (forward never crosses, or backward never
            # synchronized) → fail closed, no fabricated width. INV-ES1 vacuous.
            hysteresis = math.nan
            transition_detected = False

        if math.isfinite(hysteresis):
            K_span = self._K_range[1] - self._K_range[0]
            # bounds: proximity is a [0, 1] normalized ratio; cap at 1.0 only.
            proximity = min(hysteresis / K_span, 1.0)
            is_explosive = hysteresis > self._hyst_thresh
        else:
            proximity = 0.0
            is_explosive = False

        return ESProximityResult(
            R_forward=R_forward,
            R_backward=R_backward,
            K_values=K_values,
            K_c_forward=K_c_fwd,
            K_c_backward=K_c_bwd,
            hysteresis_width=hysteresis,
            proximity=proximity,
            is_explosive=is_explosive,
            transition_detected=transition_detected,
            hysteresis_is_lower_bound=hysteresis_is_lower_bound,
        )

    def _find_critical_K(
        self,
        K_values: NDArray[np.float64],
        R_values: NDArray[np.float64],
    ) -> float:
        """Find K_c where R crosses the synchronization threshold.

        Returns the linearly-interpolated K at the first upward crossing of
        ``R_threshold``. If R(K) never crosses the threshold (flat/monotone
        sub-threshold, or already-saturated above threshold across the whole
        sweep) there is NO observable transition on this grid, so we return
        ``nan`` — a sentinel for "transition not detected".

        Fail-closed rationale: the previous behaviour returned a sweep ENDPOINT
        (``K_values[0]`` or ``K_values[-1]``) when no crossing existed. That
        fabricated a K_c from the grid boundary, so the downstream hysteresis
        ``|K_c_fwd − K_c_bwd|`` was computed from artifacts and could trip the
        ESCircuitBreaker on a non-existent transition (fail-OPEN). Returning nan
        forces the caller to mark the result as not-detected (is_explosive=False,
        proximity=0.0) — no fabricated transition.
        """
        crossings = np.where((R_values[:-1] < self._R_thresh) & (R_values[1:] >= self._R_thresh))[0]
        if crossings.size > 0:
            idx = crossings[0]
            # Linear interpolation between the two bracketing grid points.
            frac = (self._R_thresh - R_values[idx]) / max(R_values[idx + 1] - R_values[idx], 1e-12)
            return float(K_values[idx] + frac * (K_values[idx + 1] - K_values[idx]))
        # No threshold crossing on this grid → no real transition. Fail closed:
        # return nan sentinel instead of a grid-boundary K_c. bounds: nan is the
        # explicit "transition not detected" signal; callers must not treat it as
        # a finite K_c (see measure_proximity / transition_detected).
        return math.nan

    def crisis_signal(
        self,
        prices: NDArray[np.float64],
        window: int = 60,
        correlation_threshold: float = 0.3,
    ) -> ESProximityResult:
        """Compute ES proximity from price data.

        Builds correlation-based adjacency from rolling returns,
        then measures hysteresis.
        """
        prices = np.asarray(prices, dtype=np.float64)
        if prices.ndim != 2 or prices.shape[0] < window:
            raise ValueError(f"Need (T≥{window}, N) array, got {prices.shape}")

        returns = np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12)
        tail = returns[-window:]
        N = prices.shape[1]

        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(tail, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0)

        # Build adjacency
        adj = np.abs(corr)
        adj[adj < correlation_threshold] = 0.0
        np.fill_diagonal(adj, 0.0)

        # Use return-derived natural frequencies. Each oscillator's mean per-bar
        # return is converted to an angular velocity ω [rad / integration-time-
        # unit] via the documented unit bridge ω = mean_return / _INTEGRATION_DT
        # (= mean_return · _RETURN_TO_OMEGA). This is the derivation of the former
        # magic "* 100": it is exactly 1/dt, NOT a tuning constant.
        omega = np.mean(tail, axis=0) * _RETURN_TO_OMEGA

        return self.measure_proximity(adjacency=adj, omega=omega, N=N)


class ESCircuitBreaker:
    """Circuit breaker that triggers on explosive sync proximity.

    Parameters
    ----------
    proximity_threshold : float
        ES proximity above which to trigger (default 0.15).
    cooldown_steps : int
        Steps to wait before re-arming after trigger (default 10).
    """

    def __init__(
        self,
        proximity_threshold: float = 0.15,
        cooldown_steps: int = 10,
    ) -> None:
        if not 0 < proximity_threshold < 1:
            raise ValueError(f"threshold must be in (0, 1), got {proximity_threshold}")
        self._threshold = proximity_threshold
        self._cooldown = cooldown_steps
        self._triggered = False
        self._cooldown_remaining = 0
        self._trigger_count = 0

    @property
    def is_triggered(self) -> bool:
        return self._triggered

    @property
    def trigger_count(self) -> int:
        return self._trigger_count

    def check(self, proximity: float) -> bool:
        """Check if circuit breaker should trigger.

        Returns True if trading should be HALTED.
        """
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            if self._cooldown_remaining == 0:
                self._triggered = False
            return self._triggered

        if proximity > self._threshold:
            self._triggered = True
            self._cooldown_remaining = self._cooldown
            self._trigger_count += 1
            return True

        self._triggered = False
        return False

    def reset(self) -> None:
        """Reset circuit breaker state."""
        self._triggered = False
        self._cooldown_remaining = 0


__all__ = [
    "ExplosiveSyncDetector",
    "ESProximityResult",
    "ESCircuitBreaker",
]
