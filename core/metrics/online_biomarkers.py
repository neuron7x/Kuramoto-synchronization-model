"""Online biomarker monitoring with sliding window DFA and fractional diffusion.

Implements real-time monitoring algorithms for α_agent and fractional dynamics
as recommended in the 2025 audit for continual learning stability.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class BiomarkerState:
    """Current state of online biomarker monitoring."""

    alpha: float
    alpha_target_low: float
    alpha_target_high: float
    holder_exponent: float
    retention_metric: float
    backward_transfer: float
    convergence_rate: float


class OnlineBiomarkerMonitor:
    """Real-time biomarker monitoring with sliding window DFA-α estimation.
    
    Addresses audit weakness: "брак онлайн-алгоритмів для real-time моніторингу"
    Implements sliding window for α_agent tracking with target range [0.8, 1.0].
    """

    def __init__(
        self,
        window_size: int = 2000,
        min_win: int = 50,
        max_win: int = 500,
        n_win: int = 10,
        alpha_target: tuple[float, float] = (0.8, 1.0),
    ) -> None:
        self.window_size = window_size
        self.min_win = min_win
        self.max_win = max_win
        self.n_win = n_win
        self.alpha_target = alpha_target
        self._buffer: deque[float] = deque(maxlen=window_size)
        self._alpha_history: list[float] = []
        self._holder_history: list[float] = []

    def update(self, value: float) -> None:
        """Add new value to the sliding window buffer."""
        self._buffer.append(value)

    def compute_alpha(self) -> float | None:
        """Compute DFA-α on current buffer using sliding window.
        
        Returns None if insufficient data, otherwise α ∈ [0, 1.5].
        """
        if len(self._buffer) < self.min_win * 2:
            return None

        data = np.array(self._buffer, dtype=float)
        
        # Generate window sizes logarithmically
        windows = np.unique(
            np.geomspace(self.min_win, min(self.max_win, len(data) // 2), num=self.n_win).astype(int)
        )
        windows = windows[windows > 1]
        windows = windows[windows <= len(data) // 2]
        
        if len(windows) < 2:
            return None

        fluctuations = []
        for window in windows:
            # Detrended fluctuation analysis
            n_segments = len(data) // window
            if n_segments < 1:
                continue
            
            trimmed = data[: n_segments * window].reshape(n_segments, window)
            
            # Detrend each segment
            trends = np.polyfit(np.arange(window), trimmed.T, 1)
            # trends[0] is slope (n_segments,), trends[1] is intercept (n_segments,)
            time_axis = np.arange(window)
            detrended = trimmed - (trends[0][:, np.newaxis] * time_axis + trends[1][:, np.newaxis])
            
            # Root mean square fluctuation
            fluct = np.sqrt(np.mean(detrended ** 2))
            fluctuations.append(fluct)

        if len(fluctuations) < 2 or not all(np.isfinite(fluctuations)):
            return None

        # Log-log regression
        log_windows = np.log(windows[: len(fluctuations)])
        log_fluct = np.log(np.array(fluctuations) + 1e-10)
        
        valid = np.isfinite(log_fluct) & (log_fluct > -10)
        if valid.sum() < 2:
            return None
            
        slope, _ = np.polyfit(log_windows[valid], log_fluct[valid], 1)
        alpha = float(np.clip(slope, 0.0, 1.5))
        
        self._alpha_history.append(alpha)
        return alpha

    def compute_holder_exponent(self, series: Iterable[float]) -> float:
        """Compute Hölder exponent for EoS-stability as per audit recommendation.
        
        Implements fractional diffusion approach for energy market noise resilience.
        """
        data = np.asarray(series, dtype=float)
        if len(data) < 4:
            return 0.5

        # Local Hölder exponent via increments
        increments = np.abs(np.diff(data))
        if len(increments) < 2:
            return 0.5
        
        # Log-log slope of increments
        scales = np.arange(1, min(len(increments), 20))
        variances = []
        
        for scale in scales:
            if scale >= len(increments):
                break
            windowed = increments[: len(increments) - len(increments) % scale]
            reshaped = windowed.reshape(-1, scale)
            var = np.mean(np.sum(reshaped, axis=1) ** 2)
            variances.append(var)
        
        if len(variances) < 2:
            return 0.5
        
        log_scales = np.log(scales[: len(variances)])
        log_vars = np.log(np.array(variances) + 1e-10)
        
        valid = np.isfinite(log_vars)
        if valid.sum() < 2:
            return 0.5
        
        slope, _ = np.polyfit(log_scales[valid], log_vars[valid], 1)
        holder = float(np.clip(slope / 2.0, 0.0, 1.0))
        
        self._holder_history.append(holder)
        return holder

    def is_in_target_range(self, alpha: float) -> bool:
        """Check if α is within target range [0.8, 1.0]."""
        return self.alpha_target[0] <= alpha <= self.alpha_target[1]

    def detect_white_noise(self, alpha: float | None, threshold: float = 0.55) -> bool:
        """Detect non-fractal regime (white noise) when α → 0.5.
        
        Addresses audit weakness: "відсутність fallback для нефрактальних режимів"
        """
        if alpha is None:
            return True
        return abs(alpha - 0.5) < threshold - 0.5

    def get_state(self) -> BiomarkerState:
        """Return current biomarker state for monitoring."""
        alpha = self._alpha_history[-1] if self._alpha_history else 0.5
        holder = self._holder_history[-1] if self._holder_history else 0.5
        
        # Compute retention metric (α stability over time)
        retention = 1.0
        if len(self._alpha_history) >= 10:
            recent = np.array(self._alpha_history[-10:])
            retention = float(1.0 - np.std(recent))
        
        # Backward transfer (improvement in α from initial)
        backward_transfer = 0.0
        if len(self._alpha_history) >= 2:
            initial_alpha = self._alpha_history[0]
            current_alpha = self._alpha_history[-1]
            backward_transfer = float(current_alpha - initial_alpha)
        
        # Convergence rate (α approaching target faster)
        convergence_rate = 0.0
        if len(self._alpha_history) >= 5:
            recent_alphas = np.array(self._alpha_history[-5:])
            target_center = sum(self.alpha_target) / 2
            distances = np.abs(recent_alphas - target_center)
            if len(distances) >= 2:
                convergence_rate = float(distances[0] - distances[-1])
        
        return BiomarkerState(
            alpha=alpha,
            alpha_target_low=self.alpha_target[0],
            alpha_target_high=self.alpha_target[1],
            holder_exponent=holder,
            retention_metric=retention,
            backward_transfer=backward_transfer,
            convergence_rate=convergence_rate,
        )


__all__ = ["OnlineBiomarkerMonitor", "BiomarkerState"]
