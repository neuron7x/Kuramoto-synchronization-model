# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Topology dislocation detector — sees fragility before price moves.

OFI sees flow. PCA sees covariance. This sees the geometry of the
space in which price exists — and detects when that space is tearing.

Dislocation = rapid topology degradation:
  κ falling (Ricci curvature collapsing = network bottleneck forming)
  + γ diverging from 1.0 (spectral structure breaking)
  + R spiking (herding = everyone running the same direction)

Topology fragility signal — temporal relationship requires empirical calibration.
This is the function that converts topology into capital.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DislocationState:
    """Topology dislocation assessment at one time step."""

    kappa_velocity: float  # dκ/dt: rate of curvature change
    gamma_velocity: float  # dγ/dt: rate of spectral drift
    r_acceleration: float  # d²R/dt²: sync acceleration (herding onset)
    dislocation_score: float  # composite [0, 1]: 0=stable, 1=tearing
    is_pre_dislocation: bool  # True if topology degrading but price hasn't moved
    lead_bars: int  # estimated bars until topology impact (uncalibrated)


class DislocationDetector:
    """Detects topology fragility before market dislocation.

    Tracks velocity and acceleration of κ, γ, R to identify
    the moment when network structure begins to tear — typically
    Temporal offset pending calibration on real tick data.

    Parameters
    ----------
    window
        Rolling window for velocity estimation.
    kappa_threshold
        κ velocity below which topology is degrading.
    gamma_threshold
        γ velocity above which spectral structure is breaking.
    r_threshold
        R acceleration above which herding is forming.
    """

    def __init__(
        self,
        *,
        window: int = 20,
        kappa_threshold: float = -0.05,
        gamma_threshold: float = 0.1,
        r_threshold: float = 0.02,
    ) -> None:
        self._window = window
        self._kappa_threshold = kappa_threshold
        self._gamma_threshold = gamma_threshold
        self._r_threshold = r_threshold

        self._kappa_history: deque[float] = deque(maxlen=window)
        self._gamma_history: deque[float] = deque(maxlen=window)
        self._r_history: deque[float] = deque(maxlen=window)

    def update(
        self,
        *,
        kappa: float,
        gamma: float,
        order_r: float,
    ) -> DislocationState:
        """Ingest one signal tick, return dislocation assessment."""
        kappa = _sanitize(kappa, 0.0)
        gamma = _sanitize(gamma, 1.0)
        order_r = max(0.0, min(1.0, _sanitize(order_r, 0.0)))

        self._kappa_history.append(kappa)
        self._gamma_history.append(gamma)
        self._r_history.append(order_r)

        if len(self._kappa_history) < 5:
            return DislocationState(
                kappa_velocity=0.0,
                gamma_velocity=0.0,
                r_acceleration=0.0,
                dislocation_score=0.0,
                is_pre_dislocation=False,
                lead_bars=0,
            )

        # Velocities: finite difference over last 3 bars
        kv = _velocity(self._kappa_history)
        gv = _velocity(self._gamma_history)

        # R acceleration: second derivative
        ra = _acceleration(self._r_history)

        # Dislocation score: weighted composite
        # Normalize by recent range for adaptive sensitivity
        kappa_range = max(self._kappa_history) - min(self._kappa_history) + 1e-9
        kappa_signal = max(0.0, -kv / kappa_range * 2.0)

        # γ drifting = spectral instability (weight 0.3)
        gamma_range = max(self._gamma_history) - min(self._gamma_history) + 1e-9
        gamma_signal = max(0.0, abs(gv) / gamma_range * 2.0)

        # R accelerating = herding onset (weight 0.3)
        r_range = max(self._r_history) - min(self._r_history) + 1e-9
        r_signal = max(0.0, ra / r_range * 2.0)

        score = min(1.0, 0.4 * kappa_signal + 0.3 * gamma_signal + 0.3 * r_signal)

        # Pre-dislocation: topology degrading but not yet critical
        is_pre = score > 0.3 and kv < self._kappa_threshold

        # Topology degradation horizon: based on κ velocity (uncalibrated)
        if kv < -0.01:
            lead = min(15, max(3, int(abs(kappa) / abs(kv))))
        else:
            lead = 0

        return DislocationState(
            kappa_velocity=kv,
            gamma_velocity=gv,
            r_acceleration=ra,
            dislocation_score=round(score, 4),
            is_pre_dislocation=is_pre,
            lead_bars=lead,
        )


def _velocity(history: deque[float]) -> float:
    """Finite difference velocity over last 3 values."""
    if len(history) < 3:
        return 0.0
    vals = list(history)
    return (vals[-1] - vals[-3]) / 2.0


def _sanitize(value: float, fallback: float) -> float:
    """Ensure finite input for physics pipeline."""
    return value if math.isfinite(value) else fallback


def _acceleration(history: deque[float]) -> float:
    """Second derivative over last 5 values."""
    if len(history) < 5:
        return 0.0
    vals = list(history)
    v1 = vals[-1] - vals[-2]
    v2 = vals[-3] - vals[-4]
    return v1 - v2
