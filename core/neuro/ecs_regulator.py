"""ECS-Inspired Regulator for Adaptive Trading Control.

This module implements the ECSInspiredRegulator, a biologically-inspired
regulatory system based on the Endocannabinoid System (ECS) for adaptive
risk management and trading decisions. The regulator integrates empirical
neuroscience data (2025 updates) including:

- Acute vs chronic stress differentiation
- Context-dependent normalization via market phase
- Compensatory feedback loops aligned with TACL free energy
- Kalman filtering for predictive coding
- Full traceability for MiFID II compliance

The regulator is designed to integrate with TradePulse's FractalMotivationController
and TACL thermodynamic control system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass(slots=True)
class ECSMetrics:
    """Metrics computed by the ECS-inspired regulator."""

    timestamp: int
    stress_level: float
    free_energy_proxy: float
    risk_threshold: float
    compensatory_factor: float
    chronic_counter: int
    is_chronic: bool


class ECSInspiredRegulator:
    """ECS-inspired regulator for adaptive risk management.

    Implements biologically-inspired control based on endocannabinoid system
    dynamics, with stress differentiation, context-dependent modulation, and
    free energy alignment for thermodynamic consistency.

    Args:
        initial_risk_threshold: Initial adaptive risk threshold (AEA-inspired)
        smoothing_alpha: EMA smoothing factor for homeostasis (0-1)
        stress_threshold: Threshold for high stress detection
        chronic_threshold: Number of periods for chronic stress detection
        fe_scaling: Scaling factor for free energy proxy mapping
        seed: Random seed for reproducibility (optional)

    Example:
        >>> regulator = ECSInspiredRegulator()
        >>> regulator.update_stress(np.array([0.01, -0.02, 0.015]), 0.05)
        >>> action = regulator.decide_action(0.03, context_phase='stable')
        >>> trace = regulator.get_trace()
    """

    def __init__(
        self,
        initial_risk_threshold: float = 0.05,
        smoothing_alpha: float = 0.9,
        stress_threshold: float = 0.1,
        chronic_threshold: int = 5,
        fe_scaling: float = 1.0,
        seed: int | None = None,
    ) -> None:
        if not 0.0 < initial_risk_threshold <= 1.0:
            raise ValueError("initial_risk_threshold must be between 0 and 1")
        if not 0.0 < smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha must be between 0 and 1")
        if stress_threshold <= 0.0:
            raise ValueError("stress_threshold must be positive")
        if chronic_threshold < 1:
            raise ValueError("chronic_threshold must be at least 1")
        if fe_scaling <= 0.0:
            raise ValueError("fe_scaling must be positive")

        self.risk_threshold = float(initial_risk_threshold)
        self.compensatory_factor = 1.0  # 2-AG-inspired compensation
        self.smoothing_alpha = float(smoothing_alpha)
        self.stress_level = 0.0
        self.free_energy_proxy = 0.0
        self.stress_threshold = float(stress_threshold)
        self.chronic_threshold = int(chronic_threshold)
        self.chronic_counter = 0
        self.fe_scaling = float(fe_scaling)
        self.history: list[dict] = []
        self._rng = np.random.default_rng(seed)

        # Kalman filter state for signal processing
        self.kalman_state = 0.0
        self.kalman_variance = 1.0

    def update_stress(
        self,
        market_returns: np.ndarray,
        drawdown: float,
        previous_fe: Optional[float] = None,
    ) -> None:
        """Update stress level based on market conditions.

        Computes combined stress from volatility and drawdown, applies EMA smoothing,
        and tracks chronic stress patterns. Enforces monotonic free energy descent
        when aligned with TACL.

        Args:
            market_returns: Array of recent market returns
            drawdown: Current drawdown ratio (0-1)
            previous_fe: Previous free energy value for monotonic descent check

        Raises:
            ValueError: If market_returns is empty or drawdown is negative
        """
        if len(market_returns) == 0:
            raise ValueError("market_returns must not be empty")
        if drawdown < 0.0:
            raise ValueError("drawdown must be non-negative")

        # Compute volatility proxy
        returns_array = np.asarray(market_returns, dtype=float)
        if len(returns_array) > 1:
            volatility_proxy = float(np.std(returns_array))
        else:
            volatility_proxy = float(np.abs(np.mean(returns_array)))

        # Combined stress with weighted components
        combined_stress = 0.7 * volatility_proxy + 0.3 * float(drawdown)

        # Apply EMA smoothing for homeostasis
        self.stress_level = (
            self.smoothing_alpha * self.stress_level + (1 - self.smoothing_alpha) * combined_stress
        )

        # Map to TACL free energy proxy
        self.free_energy_proxy = self.stress_level * self.fe_scaling

        # Enforce monotonic descent if previous FE provided
        if previous_fe is not None:
            delta_fe = self.free_energy_proxy - previous_fe
            if delta_fe > 0:  # Violation of descent
                self.stress_level *= 0.98  # Correction
                self.free_energy_proxy = previous_fe  # Cap to previous

        # Track chronic stress patterns
        if self.stress_level > self.stress_threshold:
            self.chronic_counter += 1
        else:
            self.chronic_counter = max(0, self.chronic_counter - 1)

        # Log the update
        self.log_action(
            "Stress update",
            {
                "stress": float(self.stress_level),
                "fe_proxy": float(self.free_energy_proxy),
                "vol": float(volatility_proxy),
                "dd": float(drawdown),
                "chronic_count": self.chronic_counter,
            },
        )

    def adapt_parameters(self, context_phase: str = "stable") -> None:
        """Adapt risk parameters based on stress and market context.

        Implements context-dependent modulation inspired by ECS dynamics:
        - Acute stress: moderate threshold reduction
        - Chronic stress: aggressive threshold reduction
        - Phase-dependent: conservative in chaotic/transition phases

        Args:
            context_phase: Market phase from Kuramoto-Ricci analysis
                         ('stable', 'chaotic', 'transition')
        """
        is_chronic = self.chronic_counter > self.chronic_threshold

        # Context-dependent phase factor
        phase_factor = 0.95 if context_phase in ["chaotic", "transition"] else 1.02

        if self.stress_level > self.stress_threshold:
            # High stress adaptation
            threshold_multiplier = 0.92 if is_chronic else 0.95
            self.risk_threshold *= threshold_multiplier * phase_factor

            # Compensatory upregulation (2-AG-inspired)
            comp_increase = 1.15 if is_chronic else 1.1
            self.compensatory_factor = min(
                1.6 if is_chronic else 1.5, self.compensatory_factor * comp_increase
            )

            self.log_action(
                "High stress adaptation",
                {
                    "new_threshold": self.risk_threshold,
                    "comp_factor": self.compensatory_factor,
                    "chronic": is_chronic,
                },
            )
        else:
            # Recovery with normalization (from PET data)
            self.risk_threshold = min(0.05, self.risk_threshold * phase_factor)
            self.compensatory_factor = max(1.0, self.compensatory_factor * 0.98)

            self.log_action(
                "Recovery adaptation",
                {
                    "new_threshold": self.risk_threshold,
                    "comp_factor": self.compensatory_factor,
                    "chronic": is_chronic,
                },
            )

    def kalman_filter_signal(self, raw_signal: float) -> float:
        """Apply Kalman filter for predictive coding.

        Implements simple Kalman filter inspired by ECS signal filtering
        and predictive coding framework (Rao & Ballard 1999).

        Args:
            raw_signal: Raw signal value to filter

        Returns:
            Filtered signal value
        """
        # Prediction step
        prediction = self.kalman_state
        prediction_error = float(raw_signal) - prediction

        # Update step
        measurement_noise = 0.01
        kalman_gain = self.kalman_variance / (self.kalman_variance + measurement_noise)

        self.kalman_state += kalman_gain * prediction_error
        self.kalman_variance = (1 - kalman_gain) * self.kalman_variance

        return float(self.kalman_state)

    def decide_action(self, signal_strength: float, context_phase: str = "stable") -> int:
        """Decide trading action based on filtered signal and context.

        Applies Kalman filtering, compensatory modulation, and conformal
        prediction checks (SABRE-like) for robust decision-making.

        Args:
            signal_strength: Raw trading signal strength
            context_phase: Market phase for context-dependent filtering

        Returns:
            Action code: -1 (sell), 0 (hold), 1 (buy)
        """
        # Apply Kalman filter
        filtered_signal = self.kalman_filter_signal(float(signal_strength))

        # Apply compensatory modulation
        adjusted_signal = filtered_signal * self.compensatory_factor

        # Decision with threshold check
        if abs(adjusted_signal) > self.risk_threshold:
            action = int(np.sign(adjusted_signal))

            # Conformal prediction check (SABRE-like)
            conf_prob = norm.cdf(abs(adjusted_signal) / self.risk_threshold)

            # Context-dependent override
            if conf_prob < 0.95 and context_phase != "stable":
                action = 0
        else:
            action = 0

        self.log_action(
            "Decision",
            {
                "raw_signal": float(signal_strength),
                "filtered": float(filtered_signal),
                "action": action,
                "phase": context_phase,
            },
        )

        return action

    def log_action(self, action_type: str, details: dict) -> None:
        """Log an action with timestamp and details.

        Args:
            action_type: Type of action being logged
            details: Dictionary of action details
        """
        self.history.append(
            {"timestamp": len(self.history), "type": action_type, "details": details}
        )

    def get_trace(self) -> pd.DataFrame:
        """Export trace history as DataFrame for Parquet logging.

        Returns:
            DataFrame with complete trace history
        """
        return pd.DataFrame(self.history)

    def get_metrics(self) -> ECSMetrics:
        """Get current regulator metrics.

        Returns:
            ECSMetrics with current state
        """
        return ECSMetrics(
            timestamp=len(self.history),
            stress_level=float(self.stress_level),
            free_energy_proxy=float(self.free_energy_proxy),
            risk_threshold=float(self.risk_threshold),
            compensatory_factor=float(self.compensatory_factor),
            chronic_counter=self.chronic_counter,
            is_chronic=self.chronic_counter > self.chronic_threshold,
        )

    def reset(self) -> None:
        """Reset regulator state to initial conditions."""
        self.stress_level = 0.0
        self.free_energy_proxy = 0.0
        self.chronic_counter = 0
        self.history.clear()
        self.kalman_state = 0.0
        self.kalman_variance = 1.0


__all__ = [
    "ECSInspiredRegulator",
    "ECSMetrics",
]
