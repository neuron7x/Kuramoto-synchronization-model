"""EEP-FPPA Fractal Energy Regulator for adaptive control and crisis handling.

This module implements the EEPFractalRegulator, a fractal-driven state
regulation system for energy-efficient analytics and adaptive crisis control.
The regulator computes key metrics (Hurst exponent, Power Law Exponent, Crisis
Stability Index) and optimizes system efficiency through embodied energy damping.

The regulator can be used as:
- A feature engineering step in analytics pipelines
- An adaptive system health monitor
- A drop-in alternative to thermo_controller for crisis handling
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from core.neuro.fractal import hurst_exponent, multiscale_energy


@dataclass(slots=True)
class RegulatorMetrics:
    """Metrics computed by the EEPFractalRegulator."""

    state: float
    hurst: float
    ple: float  # Power Law Exponent
    csi: float  # Crisis Stability Index
    energy_cost: float
    efficiency_delta: float


class EEPFractalRegulator:
    """Fractal energy regulator with adaptive efficiency optimization.

    The regulator maintains a sliding window of state history and computes
    fractal metrics to detect instabilities and optimize energy efficiency.
    It implements energy damping under crisis conditions and provides
    configurable thresholds for adaptation.

    Args:
        window_size: Size of the sliding window for state history (default: 100)
        embodied_baseline: Baseline energy efficiency target (default: 1.0)
        crisis_threshold: CSI threshold for crisis detection (default: 0.3)
        energy_damping: Damping factor for energy optimization (default: 0.9)
        seed: Random seed for reproducibility (optional)

    Example:
        >>> regulator = EEPFractalRegulator(window_size=50)
        >>> metrics = regulator.update_state(0.5)
        >>> print(f"Hurst: {metrics.hurst:.3f}, CSI: {metrics.csi:.3f}")
    """

    def __init__(
        self,
        *,
        window_size: int = 100,
        embodied_baseline: float = 1.0,
        crisis_threshold: float = 0.3,
        energy_damping: float = 0.9,
        seed: int | None = None,
    ) -> None:
        if window_size < 8:
            raise ValueError("window_size must be at least 8 for reliable metrics")
        if embodied_baseline <= 0.0:
            raise ValueError("embodied_baseline must be positive")
        if not 0.0 <= crisis_threshold <= 1.0:
            raise ValueError("crisis_threshold must be between 0 and 1")
        if not 0.0 <= energy_damping <= 1.0:
            raise ValueError("energy_damping must be between 0 and 1")

        self.window_size = window_size
        self.embodied_baseline = embodied_baseline
        self.crisis_threshold = crisis_threshold
        self.energy_damping = energy_damping
        self._rng = np.random.default_rng(seed)

        # State tracking with deque for O(1) operations
        self._state_history: deque[float] = deque(maxlen=window_size)
        self._energy_history: deque[float] = deque(maxlen=window_size)
        self._last_efficiency: float = 1.0

    def update_state(self, signal: float) -> RegulatorMetrics:
        """Update regulator state with a new signal value.

        Args:
            signal: New state value to process

        Returns:
            RegulatorMetrics containing computed metrics

        Raises:
            ValueError: If signal is not finite
        """
        if not np.isfinite(signal):
            raise ValueError("signal must be finite")

        # Add to state history (deque automatically handles maxlen)
        self._state_history.append(float(signal))

        # Compute metrics
        current_state = float(signal)
        hurst = self.compute_hurst()
        ple = self.compute_ple()
        csi = self.compute_csi()
        energy_cost = self._compute_energy_cost()
        efficiency_delta = self.optimize_efficiency()

        # Track energy (deque automatically handles maxlen)
        self._energy_history.append(energy_cost)

        return RegulatorMetrics(
            state=current_state,
            hurst=hurst,
            ple=ple,
            csi=csi,
            energy_cost=energy_cost,
            efficiency_delta=efficiency_delta,
        )

    def compute_hurst(self) -> float:
        """Compute Hurst exponent for current state history.

        Returns:
            Hurst exponent (0 to 1), or 0.5 if insufficient data

        The Hurst exponent characterizes long-term memory and self-similarity:
        - H < 0.5: Anti-persistent (mean-reverting)
        - H = 0.5: Random walk (no memory)
        - H > 0.5: Persistent (trending)
        """
        if len(self._state_history) < 8:
            return 0.5

        try:
            return hurst_exponent(np.array(self._state_history))
        except (ValueError, RuntimeError):
            return 0.5

    def compute_ple(self) -> float:
        """Compute Power Law Exponent (PLE) for state dynamics.

        Returns:
            PLE value indicating scaling behavior

        The PLE characterizes how fluctuations scale with observation window.
        Higher values indicate stronger power-law behavior and complexity.
        """
        if len(self._state_history) < 8:
            return 1.0

        try:
            # Compute power spectral density via autocorrelation
            data = np.array(self._state_history)
            data = data - np.mean(data)
            if np.std(data) < 1e-10:
                return 1.0

            # Estimate spectral slope
            n = len(data)
            lags = np.arange(1, min(n // 2, 50))
            autocorr = np.array(
                [np.corrcoef(data[:-lag], data[lag:])[0, 1] for lag in lags if lag < n]
            )

            if len(autocorr) < 3 or not np.any(np.isfinite(autocorr)):
                return 1.0

            # Filter finite values
            valid = np.isfinite(autocorr) & (autocorr > 0)
            if valid.sum() < 2:
                return 1.0

            log_lags = np.log(lags[valid])
            log_corr = np.log(autocorr[valid])

            # Linear fit for power law exponent
            slope, _ = np.polyfit(log_lags, log_corr, 1)
            return float(np.clip(-slope, 0.0, 3.0))

        except (ValueError, RuntimeError):
            return 1.0

    def compute_csi(self) -> float:
        """Compute Crisis Stability Index (CSI).

        Returns:
            CSI value between 0 and 1, where lower values indicate crisis

        CSI combines volatility, regime shifts, and fractal instability
        to provide an early warning system for crisis conditions.
        """
        if len(self._state_history) < 8:
            return 1.0

        try:
            data = np.array(self._state_history)

            # Component 1: Normalized volatility
            volatility = np.std(data)
            vol_component = np.exp(-volatility)

            # Component 2: Hurst deviation from random walk
            hurst = self.compute_hurst()
            hurst_component = np.exp(-abs(hurst - 0.5) / 0.25)

            # Component 3: Regime stability (change point detection)
            if len(data) >= 20:
                mid = len(data) // 2
                first_half_mean = np.mean(data[:mid])
                second_half_mean = np.mean(data[mid:])
                regime_shift = abs(first_half_mean - second_half_mean) / (
                    volatility + 1e-10
                )
                regime_component = np.exp(-regime_shift)
            else:
                regime_component = 1.0

            # Combine components
            csi = (vol_component * hurst_component * regime_component) ** (1.0 / 3.0)
            return float(np.clip(csi, 0.0, 1.0))

        except (ValueError, RuntimeError):
            return 1.0

    def _compute_energy_cost(self) -> float:
        """Compute energy cost for current state."""
        if len(self._state_history) < 2:
            return 0.0

        try:
            # Energy as multiscale increments
            energy = multiscale_energy(np.array(self._state_history))
            return float(energy)
        except (ValueError, RuntimeError):
            return 0.0

    def optimize_efficiency(self) -> float:
        """Optimize system efficiency and return efficiency delta.

        Returns:
            Change in efficiency (positive = improvement)

        Applies energy damping under crisis conditions to improve
        long-term system efficiency relative to embodied baseline.
        """
        if len(self._energy_history) < 2:
            return 0.0

        try:
            # Current efficiency relative to baseline
            avg_energy = np.mean(self._energy_history)
            if avg_energy < 1e-10:
                current_efficiency = self.embodied_baseline
            else:
                current_efficiency = self.embodied_baseline / avg_energy

            # Apply damping if in crisis
            csi = self.compute_csi()
            if csi < self.crisis_threshold:
                # Crisis mode: apply energy damping
                damped_efficiency = (
                    current_efficiency * self.energy_damping
                    + self._last_efficiency * (1 - self.energy_damping)
                )
            else:
                damped_efficiency = current_efficiency

            # Compute delta
            efficiency_delta = damped_efficiency - self._last_efficiency
            self._last_efficiency = damped_efficiency

            return float(efficiency_delta)

        except (ValueError, RuntimeError):
            return 0.0

    def get_metrics(self) -> RegulatorMetrics | None:
        """Get the most recent metrics without updating state.

        Returns:
            Most recent RegulatorMetrics, or None if no state history
        """
        if not self._state_history:
            return None

        return RegulatorMetrics(
            state=self._state_history[-1],
            hurst=self.compute_hurst(),
            ple=self.compute_ple(),
            csi=self.compute_csi(),
            energy_cost=self._energy_history[-1] if self._energy_history else 0.0,
            efficiency_delta=0.0,  # No update, so no delta
        )

    def is_in_crisis(self) -> bool:
        """Check if system is currently in crisis state.

        Returns:
            True if CSI is below crisis threshold
        """
        return self.compute_csi() < self.crisis_threshold

    def reset(self) -> None:
        """Reset regulator state and history."""
        self._state_history.clear()
        self._energy_history.clear()
        self._last_efficiency = 1.0

    def simulate_trade_cycle(
        self,
        signals: Sequence[float],
        *,
        verbose: bool = False,
    ) -> list[RegulatorMetrics]:
        """Simulate a complete trade cycle with the regulator.

        Args:
            signals: Sequence of signal values to process
            verbose: If True, print metrics at each step

        Returns:
            List of RegulatorMetrics for each signal

        Example:
            >>> regulator = EEPFractalRegulator()
            >>> signals = np.random.randn(100)
            >>> metrics = regulator.simulate_trade_cycle(signals)
            >>> crisis_count = sum(1 for m in metrics if m.csi < 0.3)
        """
        if len(signals) == 0:
            raise ValueError("signals must be non-empty")

        results: list[RegulatorMetrics] = []

        for i, signal in enumerate(signals):
            metrics = self.update_state(signal)
            results.append(metrics)

            if verbose:
                print(
                    f"Step {i + 1}: state={metrics.state:.3f}, "
                    f"H={metrics.hurst:.3f}, PLE={metrics.ple:.3f}, "
                    f"CSI={metrics.csi:.3f}, energy={metrics.energy_cost:.3f}"
                )

        return results


__all__ = [
    "EEPFractalRegulator",
    "RegulatorMetrics",
]
