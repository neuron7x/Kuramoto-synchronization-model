# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fractal cascade utilities for FHMC integration.

These helpers power the fracto-hypothalamic meta-controller by sampling
multiplicative cascades and coloured noise series used in adaptive sleep/wake
scheduling.  The implementation favours clarity over micro-optimisation so it
can be reused in research notebooks as well as production control loops.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


class DyadicPMCascade:
    """Dyadic p-model multiplicative cascade for multifractal intervals.

    The ``heavy_tail`` parameter modulates the variability of the generated
    intervals: larger values skew the distribution towards rare but elongated
    windows.  ``base_dt`` controls the base sampling period in seconds.

    The cascade also supports Hölder exponent estimation via wavelet analysis,
    as specified in the FHMC documentation.
    """

    def __init__(
        self,
        depth: int = 12,
        p: float = 0.6,
        *,
        heavy_tail: float = 0.5,
        base_dt: float = 60.0,
        rng: np.random.Generator | None = None,
    ) -> None:
        if not (0.0 < p < 1.0):
            raise ValueError("p must be in (0, 1)")
        if depth <= 0:
            raise ValueError("depth must be positive")
        if not (0.0 <= heavy_tail <= 1.0):
            raise ValueError("heavy_tail must be within [0, 1]")
        if base_dt <= 0:
            raise ValueError("base_dt must be positive")

        self.depth = int(depth)
        self.p = float(p)
        self.heavy_tail = float(heavy_tail)
        self.base_dt = float(base_dt)
        self._rng = rng or np.random.default_rng()

    def sample(self, n: int = 256) -> np.ndarray:
        """Generate ``n`` interval samples in seconds.

        The dyadic cascade repeatedly splits the unit mass with a locally
        perturbed ``p`` value.  The resulting weights are re-scaled so their
        mean equals one, preserving the expected cadence when applied to
        scheduling windows.
        """

        if n <= 0:
            raise ValueError("n must be positive")

        weights = np.ones(1, dtype=float)
        for _ in range(self.depth):
            jitter = (self._rng.random() - 0.5) * 0.2 * self.heavy_tail
            p = float(np.clip(self.p + jitter, 1e-3, 1.0 - 1e-3))
            weights = np.kron(weights, np.array([p, 1.0 - p], dtype=float))

        weights = weights / float(weights.mean())
        intervals = np.maximum(self.base_dt * weights[:n], 1.0)
        return intervals.astype(float)

    def adjust_heavy_tail(self, delta: float) -> None:
        """Adapt the heavy-tail coefficient while respecting bounds."""

        self.heavy_tail = float(np.clip(self.heavy_tail + float(delta), 0.0, 1.0))

    def holder_field(self, n: int = 256) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate local Hölder exponents from the cascade weights.

        The Hölder field characterizes local regularity of the multiplicative
        cascade at each position. This implements the wavelet-based estimation
        mentioned in the FHMC specification (Hӧlder-поля оцінюються з
        вейвлет-коефіцієнтів).

        Args:
            n: Number of positions to estimate.

        Returns:
            Tuple of (positions, holder_values) where positions are indices
            and holder_values are the local Hölder exponents.
        """
        from core.metrics.holder import local_holder_spectrum

        # Generate cascade samples
        samples = self.sample(max(n, 64))

        # Compute local Hölder spectrum
        window = min(32, len(samples) // 4)
        window = max(16, window)

        positions, h_values = local_holder_spectrum(samples, window=window)

        # Truncate to requested size
        mask = positions < n
        return positions[mask], h_values[mask]

    def theoretical_holder(self) -> float:
        """Compute theoretical Hölder exponent for the p-model cascade.

        For a binomial cascade with parameter p, the minimum Hölder exponent
        is related to p: h_min = -log(max(p, 1-p)) / log(2).

        Returns:
            Theoretical minimum Hölder exponent for the cascade parameters.
        """
        p_max = max(self.p, 1.0 - self.p)
        return -np.log(p_max) / np.log(2.0)


def pink_noise(n: int, beta: float = 1.0, rng: np.random.Generator | None = None) -> np.ndarray:
    """Return real-valued 1/f^``beta`` noise generated via spectral shaping."""

    if n <= 0:
        raise ValueError("n must be positive")

    rng = rng or np.random.default_rng()
    white = rng.normal(size=n)
    freqs = np.fft.rfftfreq(n)
    amplitudes = np.ones_like(freqs)
    if freqs.size > 1:
        amplitudes[1:] = 1.0 / np.power(freqs[1:], beta / 2.0)

    spectrum = np.fft.rfft(white)
    shaped = spectrum * amplitudes
    signal = np.fft.irfft(shaped, n=n).real
    signal = (signal - signal.mean()) / (signal.std() + 1e-8)
    return signal.astype(float)
