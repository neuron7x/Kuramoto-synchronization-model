# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automatic phase transition detection via hysteresis analysis.

Implements forward-backward sweep over coupling strength K to identify
the critical coupling K_c at which spontaneous synchronization emerges.
This is the Kuramoto bifurcation point — the most important diagnostic
for any oscillator network.

Theory:
    For all-to-all coupling with Lorentzian g(ω):
        K_c = 2 / (π · g(0))

    For Gaussian g(ω) with std σ:
        K_c ≈ 2σ · √(2/π) ≈ 1.596 · σ

Usage::

    from core.kuramoto.phase_transition import PhaseTransitionAnalyzer
    analyzer = PhaseTransitionAnalyzer(N=200, seed=42)
    report = analyzer.sweep(K_range=(0.0, 5.0), n_points=50)
    print(f"Critical coupling: K_c = {report.K_c:.4f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig
from .engine import KuramotoEngine

__all__ = ["PhaseTransitionAnalyzer", "PhaseTransitionReport"]

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PhaseTransitionReport:
    """Results of a forward-backward hysteresis sweep."""

    K_values: NDArray[np.float64]
    R_forward: NDArray[np.float64]
    R_backward: NDArray[np.float64]
    K_c_forward: float
    K_c_backward: float
    K_c: float  # midpoint estimate
    hysteresis_width: float
    N: int
    omega_std: float
    K_c_theoretical: float  # Gaussian approximation
    metadata: dict[str, Any] = field(default_factory=dict)


class PhaseTransitionAnalyzer:
    """Forward-backward sweep to locate critical coupling K_c.

    Parameters
    ----------
    N : int
        Number of oscillators.
    seed : int | None
        RNG seed for reproducible frequency draws.
    steps_per_point : int
        Integration steps at each K value (must be long enough for
        the system to reach steady state).
    dt : float
        Integration time-step.
    warmup_fraction : float
        Fraction of trajectory to discard before measuring R̄.
    """

    def __init__(
        self,
        N: int = 200,
        seed: int | None = 42,
        steps_per_point: int = 3000,
        dt: float = 0.01,
        warmup_fraction: float = 0.5,
    ) -> None:
        self._N = N
        self._seed = seed
        self._steps = steps_per_point
        self._dt = dt
        self._warmup = warmup_fraction

        rng = np.random.default_rng(seed)
        self._omega = rng.standard_normal(N).astype(np.float64)
        self._omega_std = float(np.std(self._omega))

    def sweep(
        self,
        K_range: tuple[float, float] = (0.0, 5.0),
        n_points: int = 50,
    ) -> PhaseTransitionReport:
        """Run forward then backward sweep, return bifurcation report."""
        K_values = np.linspace(K_range[0], K_range[1], n_points)

        _logger.info(
            "Phase transition sweep: N=%d, K=[%.2f, %.2f], %d points",
            self._N,
            K_range[0],
            K_range[1],
            n_points,
        )

        R_forward = self._directional_sweep(K_values, direction="forward")
        R_backward = self._directional_sweep(K_values[::-1], direction="backward")[::-1]

        K_c_fwd = self._find_critical_K(K_values, R_forward)
        K_c_bwd = self._find_critical_K(K_values, R_backward)
        K_c_mid = (K_c_fwd + K_c_bwd) / 2.0

        # Theoretical: K_c ≈ 2σ√(2/π) for Gaussian ω
        K_c_theo = 2.0 * self._omega_std * np.sqrt(2.0 / np.pi)

        report = PhaseTransitionReport(
            K_values=K_values,
            R_forward=R_forward,
            R_backward=R_backward,
            K_c_forward=K_c_fwd,
            K_c_backward=K_c_bwd,
            K_c=K_c_mid,
            hysteresis_width=abs(K_c_fwd - K_c_bwd),
            N=self._N,
            omega_std=self._omega_std,
            K_c_theoretical=K_c_theo,
            metadata={
                "steps_per_point": self._steps,
                "dt": self._dt,
                "warmup_fraction": self._warmup,
                "seed": self._seed,
            },
        )

        _logger.info(
            "Phase transition detected: K_c=%.4f (fwd=%.4f, bwd=%.4f), "
            "hysteresis=%.4f, theoretical=%.4f",
            K_c_mid,
            K_c_fwd,
            K_c_bwd,
            report.hysteresis_width,
            K_c_theo,
        )

        return report

    def _directional_sweep(
        self,
        K_values: NDArray[np.float64],
        direction: str,
    ) -> NDArray[np.float64]:
        """Sweep K values, carrying forward the final state as IC for next K."""
        R_steady = np.zeros(len(K_values), dtype=np.float64)
        theta_carry: NDArray[np.float64] | None = None

        for i, K in enumerate(K_values):
            cfg = KuramotoConfig(
                N=self._N,
                K=float(K),
                omega=self._omega.copy(),
                dt=self._dt,
                steps=self._steps,
                theta0=theta_carry,
                seed=self._seed if theta_carry is None else None,
            )
            result = KuramotoEngine(cfg).run()

            warmup_idx = int(self._steps * self._warmup)
            R_steady[i] = float(result.order_parameter[warmup_idx:].mean())
            theta_carry = result.phases[-1].copy()

            if i % 10 == 0:
                _logger.debug("%s sweep: K=%.3f, R̄=%.4f", direction, K, R_steady[i])

        return R_steady

    @staticmethod
    def _find_critical_K(
        K_values: NDArray[np.float64],
        R_values: NDArray[np.float64],
        threshold: float = 0.3,
    ) -> float:
        """Find K where R first crosses threshold (linear interpolation).

        Fail-closed on a single-point sweep (no slope to locate K_c) and signal
        an absent transition explicitly (NaN) for a flat, never-crossing R
        curve rather than silently returning the left endpoint.
        """
        if len(R_values) < 2:
            raise ValueError(f"need ≥2 sweep points to locate K_c; got {len(R_values)}")
        for i in range(1, len(R_values)):
            if R_values[i - 1] < threshold <= R_values[i]:
                # Linear interpolation
                frac = (threshold - R_values[i - 1]) / (R_values[i] - R_values[i - 1] + 1e-15)
                return float(K_values[i - 1] + frac * (K_values[i] - K_values[i - 1]))
        # No crossing: a flat R curve has no transition in this window — signal
        # it explicitly instead of reporting a spurious K_c at the left endpoint.
        if float(np.ptp(R_values)) < 1e-9:
            return float("nan")
        # Fallback: return K at max dR/dK (a real but unthresholded transition).
        dR = np.gradient(R_values, K_values)
        return float(K_values[np.argmax(dR)])
