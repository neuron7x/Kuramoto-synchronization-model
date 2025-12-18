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

Enhanced features (2025 refactor):
- Strict monotonic free energy descent with Lyapunov-like stability guarantees
- Conservative risk aversion during high volatility periods
- Dynamic real-time adaptation via feedback loops
- Bounded gradients and mathematical stability checks

The regulator is designed to integrate with TradePulse's FractalMotivationController
and TACL thermodynamic control system.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

import numpy as np
import pandas as pd

# Mathematical constants for stability and safety bounds
GRADIENT_BOUND_MAX: float = 0.5  # Maximum allowed gradient magnitude
GRADIENT_BOUND_MIN: float = -0.5  # Minimum allowed gradient (descent)
FE_STABILITY_EPSILON: float = 1e-4  # Numerical stability epsilon (practical threshold)
VOLATILITY_SPIKE_THRESHOLD: float = 0.15  # High volatility detection
RISK_AVERSION_MULTIPLIER: float = 0.7  # Conservative multiplier during stress
FE_DECAY_FACTOR: float = 0.995  # Decay factor for monotonicity correction
SIGNAL_BOUND_MAX: float = 10.0  # Maximum allowed signal magnitude
INSTABILITY_PENALTY: float = 1.2  # Threshold increase when system unstable
FE_VARIANCE_THRESHOLD: float = 0.1  # Variance threshold for stability detection
RECOVERY_SMOOTHING_FACTOR: float = 10.0  # Controls recovery speed (higher = slower)

# Trace and conformal defaults
TRACE_SCHEMA_VERSION = "1.0"
TRACE_EMPTY_HASH = "0" * 64

# Audit-grade trace schema fields (for consistency between implementation and tests)
TRACE_SCHEMA_FIELDS = frozenset({
    "timestamp_utc", "schema_version", "decision_id", "prev_hash",
    "mode", "stress_level", "chronic_counter", "free_energy_proxy",
    "raw_signal", "filtered_signal", "adjusted_signal",
    "conformal_q", "prediction_interval_low", "prediction_interval_high",
    "conformal_ready", "action", "confidence_gate_pass", "reason_codes",
    "params_snapshot", "mode_context", "stress_level_context", "event_hash",
})


class StressMode(str, Enum):
    """Stress operating modes for conservative behavior."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    CRISIS = "CRISIS"


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


@dataclass(slots=True)
class StabilityMetrics:
    """Extended metrics for mathematical stability monitoring.

    Provides detailed insight into the regulator's thermodynamic state
    and stability guarantees for operational monitoring.
    """

    monotonicity_violations: int
    gradient_clipping_events: int
    lyapunov_value: float
    stability_margin: float
    volatility_regime: str
    risk_aversion_active: bool


class ECSInspiredRegulator:
    """ECS-inspired regulator for adaptive risk management.

    Implements biologically-inspired control based on endocannabinoid system
    dynamics, with stress differentiation, context-dependent modulation, and
    free energy alignment for thermodynamic consistency.

    Enhanced with:
    - Strict monotonic free energy descent enforcement (Lyapunov stability)
    - Conservative risk aversion during high volatility periods
    - Dynamic real-time feedback loop for adaptive risk parameters
    - Bounded gradients and mathematical stability checks

    Args:
        initial_risk_threshold: Initial adaptive risk threshold (AEA-inspired)
        smoothing_alpha: EMA smoothing factor for homeostasis (0-1)
        stress_threshold: Threshold for high stress detection
        chronic_threshold: Number of periods for chronic stress detection
        fe_scaling: Scaling factor for free energy proxy mapping
        seed: Random seed for reproducibility (optional)
        enforce_monotonicity: If True, strictly enforce FE descent (default: True)
        volatility_adaptive: If True, enable dynamic volatility adaptation (default: True)

    Example:
        >>> regulator = ECSInspiredRegulator()
        >>> regulator.update_stress(np.array([0.01, -0.02, 0.015]), 0.05)
        >>> action = regulator.decide_action(0.03, context_phase='stable')
        >>> trace = regulator.get_trace()
    """

    def __init__(
        self,
        initial_risk_threshold: float = 0.05,
        *,
        action_threshold: Optional[float] = None,
        smoothing_alpha: float = 0.9,
        stress_threshold: float = 0.1,
        crisis_threshold: Optional[float] = None,
        chronic_threshold: int = 5,
        fe_scaling: float = 1.0,
        seed: int | None = None,
        enforce_monotonicity: bool = True,
        volatility_adaptive: bool = True,
        max_fe_step_up: float = 0.0,
        research_mode: bool = False,
        crisis_action_mode: str = "hold",
        conformal_gate_enabled: bool = True,
        calibration_window: int = 256,
        alpha: float = 0.1,
        min_calibration: int = 32,
        stress_q_multiplier: float = 1.25,
        crisis_q_multiplier: float = 1.5,
        time_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not 0.0 < initial_risk_threshold <= 1.0:
            raise ValueError("initial_risk_threshold must be between 0 and 1")
        if not 0.0 < smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha must be between 0 and 1")
        if stress_threshold <= 0.0:
            raise ValueError("stress_threshold must be positive")
        if crisis_threshold is not None and crisis_threshold <= stress_threshold:
            raise ValueError("crisis_threshold must exceed stress_threshold")
        if chronic_threshold < 1:
            raise ValueError("chronic_threshold must be at least 1")
        if fe_scaling <= 0.0:
            raise ValueError("fe_scaling must be positive")
        if max_fe_step_up < 0.0:
            raise ValueError("max_fe_step_up must be non-negative")
        if crisis_action_mode not in {"hold", "reduce_only"}:
            raise ValueError("crisis_action_mode must be 'hold' or 'reduce_only'")
        if calibration_window < 1:
            raise ValueError("calibration_window must be >= 1")
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        if min_calibration < 0:
            raise ValueError("min_calibration must be non-negative")
        if stress_q_multiplier < 1.0 or crisis_q_multiplier < 1.0:
            raise ValueError("stress multipliers must be >= 1.0 for monotonic safety")

        if action_threshold is not None:
            import warnings

            warnings.warn(
                "`action_threshold` supersedes `initial_risk_threshold` for clarity. "
                "`initial_risk_threshold` will be treated as an alias and may be "
                "deprecated in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
            threshold_value = action_threshold
        else:
            threshold_value = initial_risk_threshold

        self._initial_action_threshold = float(threshold_value)
        self.risk_threshold = float(threshold_value)
        self.compensatory_factor = 1.0  # 2-AG-inspired compensation
        self.smoothing_alpha = float(smoothing_alpha)
        self.stress_level = 0.0
        self.free_energy_proxy = 0.0
        self.stress_threshold = float(stress_threshold)
        self.crisis_threshold = (
            float(crisis_threshold)
            if crisis_threshold is not None
            else float(stress_threshold * 1.5)
        )
        self.chronic_threshold = int(chronic_threshold)
        self.chronic_counter = 0
        self.fe_scaling = float(fe_scaling)
        self.max_fe_step_up = float(max_fe_step_up)
        self.research_mode = bool(research_mode)
        self.crisis_action_mode = crisis_action_mode
        self.history: list[dict] = []
        self._rng = np.random.default_rng(seed)
        self._time_provider = time_provider or (lambda: datetime.now(timezone.utc))

        self.stress_mode: StressMode = StressMode.NORMAL

        # Kalman filter state for signal processing
        self.kalman_state = 0.0
        self.kalman_variance = 1.0

        # Enhanced stability and monotonicity tracking
        self._enforce_monotonicity = enforce_monotonicity
        self._volatility_adaptive = volatility_adaptive
        self._monotonicity_violations = 0
        self._gradient_clipping_events = 0
        self._fe_history: list[float] = []
        self._volatility_history: list[float] = []
        self._lyapunov_value = 0.0
        self._current_volatility = 0.0
        self._risk_aversion_active = False
        self._feedback_gain = 0.1  # Adaptive feedback loop gain

        # Conformal calibration state
        self._calibration_scores: deque[float] = deque(maxlen=int(calibration_window))
        self.alpha = float(alpha)
        self.min_calibration = int(min_calibration)
        self.calibration_window = int(calibration_window)
        self.conformal_gate_enabled = bool(conformal_gate_enabled)
        self._coverage_events = 0
        self._coverage_hits = 0
        self._last_conformal_q = float("nan")
        self._last_prediction_interval: tuple[float, float] | None = None
        self._last_conformal_ready = False
        self._last_confidence_gate_pass = False
        self._stress_q_multiplier = float(stress_q_multiplier)
        self._crisis_q_multiplier = float(crisis_q_multiplier)

        # Audit-grade trace
        self.history: list[dict] = []
        self._last_event_hash: str = TRACE_EMPTY_HASH
        self._last_timestamp: Optional[datetime] = None

    @property
    def action_threshold(self) -> float:
        """Alias for the action threshold (previously risk_threshold)."""

        return self.risk_threshold

    @action_threshold.setter
    def action_threshold(self, value: float) -> None:
        self.risk_threshold = float(value)

    def _compute_bounded_gradient(self, new_value: float, old_value: float) -> float:
        """Compute gradient with bounds for mathematical stability.

        Applies gradient clipping to ensure bounded updates and prevent
        instability during extreme market conditions.

        Args:
            new_value: New computed value
            old_value: Previous value

        Returns:
            Bounded gradient value
        """
        gradient = new_value - old_value

        # Apply gradient bounds for stability
        if gradient > GRADIENT_BOUND_MAX:
            self._gradient_clipping_events += 1
            return GRADIENT_BOUND_MAX
        elif gradient < GRADIENT_BOUND_MIN:
            self._gradient_clipping_events += 1
            return GRADIENT_BOUND_MIN

        return gradient

    def _compute_volatility_regime(self, volatility: float) -> str:
        """Classify current volatility into regime categories.

        Args:
            volatility: Current volatility measure

        Returns:
            Volatility regime classification
        """
        if volatility > VOLATILITY_SPIKE_THRESHOLD * 2:
            return "extreme"
        elif volatility > VOLATILITY_SPIKE_THRESHOLD:
            return "high"
        elif volatility > VOLATILITY_SPIKE_THRESHOLD * 0.5:
            return "moderate"
        else:
            return "low"

    def _compute_lyapunov_value(self) -> float:
        """Compute Lyapunov-like stability indicator.

        Uses the sum of squared free energy values as a Lyapunov function
        to ensure system stability. A decreasing Lyapunov value indicates
        stable behavior.

        Returns:
            Current Lyapunov stability value
        """
        if len(self._fe_history) < 2:
            return 0.0

        # Lyapunov function: V = (1/2) * FE^2
        # For stability, dV/dt ≤ 0
        current_fe = self._fe_history[-1]
        prev_fe = self._fe_history[-2]

        v_current = 0.5 * current_fe * current_fe
        v_prev = 0.5 * prev_fe * prev_fe

        # Delta V should be ≤ 0 for stability
        delta_v = v_current - v_prev
        return float(delta_v)

    def _apply_risk_aversion(self, base_threshold: float) -> float:
        """Apply conservative risk aversion during high volatility.

        For action thresholds, risk aversion *raises* the minimum signal
        required to take a trade. This makes the regulator more
        conservative as volatility or instability increases.

        Args:
            base_threshold: Current action threshold before adjustment

        Returns:
            Adjusted threshold with aversion applied
        """
        if not self._volatility_adaptive:
            return base_threshold

        regime = self._compute_volatility_regime(self._current_volatility)

        if regime in ["high", "extreme"]:
            self._risk_aversion_active = True
            aversion_factor = 1.0 / RISK_AVERSION_MULTIPLIER
            if regime == "extreme":
                aversion_factor *= 1.2  # Extra conservative in extreme conditions
            return base_threshold * aversion_factor
        else:
            self._risk_aversion_active = False
            return base_threshold

    def _enforce_strict_monotonic_descent(
        self, new_fe: float, previous_fe: float
    ) -> float:
        """Enforce strict monotonic free energy descent as an invariant.

        This method constrains the FE proxy value to maintain thermodynamic
        consistency (FE_t <= FE_{t-1} + max_fe_step_up). The actual stress
        level is NOT modified - only the FE proxy is constrained. This
        separation ensures that stress detection and conservative behavior
        remain responsive to actual market conditions.

        Args:
            new_fe: Newly computed free energy
            previous_fe: Previous free energy value

        Returns:
            Corrected free energy value (stress level unchanged)
        """
        if not self._enforce_monotonicity:
            return new_fe

        allowed_fe = previous_fe + self.max_fe_step_up
        if not self.research_mode:
            allowed_fe = min(allowed_fe, previous_fe + FE_STABILITY_EPSILON)

        if new_fe <= allowed_fe + FE_STABILITY_EPSILON:
            return new_fe

        self._monotonicity_violations += 1

        corrected_fe = max(0.0, allowed_fe)

        self.log_action(
            "Monotonicity correction",
            {
                "original_fe": float(new_fe),
                "corrected_fe": float(corrected_fe),
                "stress_level": float(self.stress_level),
                "allowed_fe": float(allowed_fe),
                "violation_count": self._monotonicity_violations,
            },
        )

        return float(corrected_fe)

    def _update_feedback_loop(self) -> None:
        """Update dynamic feedback loop for real-time adaptation.

        Implements an integral feedback controller that adjusts
        parameters based on accumulated error signal from the
        volatility and stress history.
        """
        if len(self._volatility_history) < 5:
            return

        # Compute recent volatility trend
        recent_vol = float(np.mean(self._volatility_history[-5:]))

        # For older volatility, use either older history or decay from recent
        if len(self._volatility_history) >= 10:
            older_vol = float(np.mean(self._volatility_history[-10:-5]))
        else:
            # Use decayed estimate when not enough history
            # Assume previous volatility was slightly lower for stability
            older_vol = recent_vol * 0.9

        # Feedback error: positive if volatility increasing
        vol_error = recent_vol - older_vol

        # Adaptive gain adjustment based on regime
        regime = self._compute_volatility_regime(self._current_volatility)
        if regime in ["high", "extreme"]:
            self._feedback_gain = min(0.3, self._feedback_gain * 1.1)
        else:
            self._feedback_gain = max(0.05, self._feedback_gain * 0.95)

        # Apply integral feedback to stress threshold
        if vol_error > 0:
            # Volatility increasing: lower stress threshold for earlier detection
            adjustment = self._feedback_gain * vol_error
            self.stress_threshold = max(
                0.01, self.stress_threshold - adjustment
            )
        else:
            # Volatility decreasing: can relax threshold slightly
            adjustment = self._feedback_gain * abs(vol_error) * 0.5
            self.stress_threshold = min(
                0.2, self.stress_threshold + adjustment
            )

    def _update_stress_mode(self) -> None:
        """Update the stress mode based on current stress level."""

        previous_mode = self.stress_mode
        if self.stress_level >= self.crisis_threshold:
            self.stress_mode = StressMode.CRISIS
        elif self.stress_level >= self.stress_threshold:
            self.stress_mode = StressMode.ELEVATED
        else:
            self.stress_mode = StressMode.NORMAL

        if previous_mode != self.stress_mode:
            self.log_action(
                "Stress mode change",
                {
                    "previous_mode": previous_mode.value,
                    "new_mode": self.stress_mode.value,
                    "stress_level": float(self.stress_level),
                    "stress_threshold": float(self.stress_threshold),
                    "crisis_threshold": float(self.crisis_threshold),
                    "reason_codes": ["stress_mode_transition"],
                },
            )

    def _stress_multiplier_factor(self) -> float:
        if self.stress_mode == StressMode.CRISIS:
            return self._crisis_q_multiplier
        if self.stress_mode == StressMode.ELEVATED:
            return self._stress_q_multiplier
        return 1.0

    def _compute_conformal_q(self, *, stress_scaled: bool = True) -> float:
        if len(self._calibration_scores) == 0:
            return float("nan")

        raw_q = float(np.quantile(self._calibration_scores, 1 - self.alpha))
        q = max(0.0, raw_q)
        if stress_scaled:
            q *= self._stress_multiplier_factor()
        return float(q)

    def get_prediction_interval(self, y_pred: float) -> tuple[float, float]:
        q = self._compute_conformal_q()
        if not np.isfinite(q):
            return (float("nan"), float("nan"))
        interval = (float(y_pred - q), float(y_pred + q))
        assert q >= 0, "conformal_q must be non-negative"
        return interval

    def update_with_realized(self, y_realized: float, y_pred: float) -> None:
        if not (np.isfinite(y_realized) and np.isfinite(y_pred)):
            return

        score = float(abs(y_realized - y_pred))
        self._calibration_scores.append(score)

        q = self._compute_conformal_q()
        if len(self._calibration_scores) >= self.min_calibration and np.isfinite(q):
            self._coverage_events += 1
            if score <= q:
                self._coverage_hits += 1

    def get_conformal_threshold(self) -> float:
        return self._compute_conformal_q()

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

        Enhanced with:
        - Strict monotonic descent enforcement
        - Bounded gradient updates
        - Lyapunov stability checks
        - Dynamic volatility adaptation

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

        # Compute volatility proxy with NaN/inf safety
        returns_array = np.asarray(market_returns, dtype=float)
        finite_mask = np.isfinite(returns_array)
        if not np.any(finite_mask):
            volatility_proxy = 0.0
        else:
            safe_returns = returns_array[finite_mask]
            if len(safe_returns) > 1:
                volatility_proxy = float(np.std(safe_returns))
            else:
                volatility_proxy = float(np.abs(np.mean(safe_returns)))

        # Track volatility for regime detection and feedback
        self._current_volatility = volatility_proxy
        self._volatility_history.append(volatility_proxy)
        if len(self._volatility_history) > 100:  # Keep last 100 values
            self._volatility_history.pop(0)

        # Apply risk aversion during high volatility
        effective_threshold = self._apply_risk_aversion(self.risk_threshold)

        # Combined stress with weighted components
        combined_stress = 0.7 * volatility_proxy + 0.3 * float(drawdown)

        # Apply bounded gradient for stability
        old_stress = self.stress_level
        new_stress = (
            self.smoothing_alpha * self.stress_level
            + (1 - self.smoothing_alpha) * combined_stress
        )

        # Bound the stress update gradient
        stress_gradient = self._compute_bounded_gradient(new_stress, old_stress)
        self.stress_level = max(0.0, old_stress + stress_gradient)

        # Map to TACL free energy proxy
        raw_fe = self.stress_level * self.fe_scaling

        # Enforce strict monotonic descent on FE proxy only.
        # Stress level is NOT modified - this ensures stress detection and
        # conservative behavior remain responsive to actual market conditions.
        if previous_fe is not None:
            self.free_energy_proxy = self._enforce_strict_monotonic_descent(
                raw_fe, previous_fe
            )
        else:
            self.free_energy_proxy = raw_fe

        # Track FE history for Lyapunov analysis
        self._fe_history.append(self.free_energy_proxy)
        if len(self._fe_history) > 100:  # Keep last 100 values
            self._fe_history.pop(0)

        # Compute Lyapunov value for stability monitoring
        self._lyapunov_value = self._compute_lyapunov_value()

        # Update stress mode after free energy correction keeps invariants aligned
        self._update_stress_mode()

        # Update dynamic feedback loop
        self._update_feedback_loop()

        # Track chronic stress patterns
        if self.stress_level > self.stress_threshold:
            self.chronic_counter += 1
        else:
            self.chronic_counter = max(0, self.chronic_counter - 1)

        # Log the update with extended metrics
        self.log_action(
            "Stress update",
            {
                "stress": float(self.stress_level),
                "fe_proxy": float(self.free_energy_proxy),
                "vol": float(volatility_proxy),
                "dd": float(drawdown),
                "chronic_count": self.chronic_counter,
                "volatility_regime": self._compute_volatility_regime(volatility_proxy),
                "risk_aversion_active": self._risk_aversion_active,
                "lyapunov_value": float(self._lyapunov_value),
                "effective_threshold": float(effective_threshold),
                "stress_mode": self.stress_mode.value,
            },
        )

    def adapt_parameters(self, context_phase: str = "stable") -> None:
        """Adapt risk parameters based on stress and market context.

        Implements context-dependent modulation inspired by ECS dynamics:
        - Acute stress: moderate threshold reduction
        - Chronic stress: aggressive threshold reduction
        - Phase-dependent: conservative in chaotic/transition phases

        Enhanced with:
        - Conservative risk aversion during high volatility
        - Bounded parameter adjustments for stability
        - Lyapunov-aware adaptation

        Args:
            context_phase: Market phase from Kuramoto-Ricci analysis
                         ('stable', 'chaotic', 'transition')
        """
        is_chronic = self.chronic_counter > self.chronic_threshold
        volatility_regime = self._compute_volatility_regime(self._current_volatility)

        # Context-dependent phase factor (values >1 harden the threshold)
        phase_factor = 1.05 if context_phase in ["chaotic", "transition"] else 1.0

        # Additional conservatism during high volatility
        if self._volatility_adaptive and volatility_regime in ["high", "extreme"]:
            phase_factor *= 1.0 / RISK_AVERSION_MULTIPLIER
            if volatility_regime == "extreme":
                phase_factor *= 1.1  # Extra conservative

        if self.stress_level > self.stress_threshold:
            # High stress adaptation
            threshold_multiplier = 1.2 if is_chronic else 1.08
            if self.stress_mode == StressMode.CRISIS:
                threshold_multiplier *= 1.2
            new_threshold = self.risk_threshold * threshold_multiplier * phase_factor

            # Bound the threshold change for stability
            max_change = 0.1 * self.risk_threshold
            if abs(new_threshold - self.risk_threshold) > max_change:
                if new_threshold < self.risk_threshold:
                    new_threshold = self.risk_threshold - max_change
                else:
                    new_threshold = self.risk_threshold + max_change

            # Ensure minimum threshold for safety
            self.risk_threshold = max(0.001, new_threshold)

            # Compensatory upregulation (2-AG-inspired)
            # Reduced compensation during high volatility for safety
            if volatility_regime in ["high", "extreme"]:
                comp_increase = 1.01 if is_chronic else 1.0
                max_comp = 1.15 if is_chronic else 1.1
            else:
                comp_increase = 1.05 if is_chronic else 1.02
                max_comp = 1.3 if is_chronic else 1.2

            self.compensatory_factor = min(
                max_comp, self.compensatory_factor * comp_increase
            )

            self.log_action(
                "High stress adaptation",
                {
                    "new_threshold": self.risk_threshold,
                    "comp_factor": self.compensatory_factor,
                    "chronic": is_chronic,
                    "volatility_regime": volatility_regime,
                    "phase_factor": float(phase_factor),
                },
            )
        else:
            # Recovery with normalization (from PET data)
            # During recovery, we gradually return threshold toward initial value
            # High volatility should SLOW recovery (not accelerate it)
            recovery_rate = 1.0

            # Slow down recovery during chaotic/transition phases
            if context_phase in ["chaotic", "transition"]:
                recovery_rate *= 1.02  # Slightly slower recovery

            # Slow down recovery during high volatility (stay conservative longer)
            if self._volatility_adaptive and volatility_regime in ["high", "extreme"]:
                recovery_rate *= 1.05  # Even slower recovery
                if volatility_regime == "extreme":
                    recovery_rate *= 1.1  # Much slower recovery

            if volatility_regime == "moderate":
                recovery_rate *= 0.98  # Slightly faster recovery in calm conditions

            recovery_target = self._initial_action_threshold
            if self.research_mode:
                recovery_target = min(self._initial_action_threshold, self.risk_threshold)

            # Gradually move threshold toward initial (recovery_target).
            # Higher recovery_rate slows recovery; RECOVERY_SMOOTHING_FACTOR
            # controls the base smoothing (higher = slower convergence).
            self.risk_threshold = max(
                0.001,
                self.risk_threshold + (recovery_target - self.risk_threshold)
                / (recovery_rate * RECOVERY_SMOOTHING_FACTOR),
            )
            self.compensatory_factor = max(1.0, self.compensatory_factor * 0.98)

            self.log_action(
                "Recovery adaptation",
                {
                    "new_threshold": self.risk_threshold,
                    "comp_factor": self.compensatory_factor,
                    "chronic": is_chronic,
                    "volatility_regime": volatility_regime,
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

    def decide_action(
        self, signal_strength: float, context_phase: str = "stable"
    ) -> int:
        """Decide trading action based on filtered signal and context.

        Applies Kalman filtering, compensatory modulation, and conformal
        prediction checks (SABRE-like) for robust decision-making.

        Enhanced with:
        - Lyapunov stability checks before action
        - Conservative override during high volatility
        - Bounded signal processing for mathematical integrity

        Args:
            signal_strength: Raw trading signal strength
            context_phase: Market phase for context-dependent filtering

        Returns:
            Action code: -1 (sell), 0 (hold), 1 (buy)
        """
        # Safety against NaN/inf signals
        if not np.isfinite(signal_strength):
            self.log_action(
                "Decision",
                {
                    "raw_signal": float("nan"),
                    "filtered": float("nan"),
                    "adjusted_signal": float("nan"),
                    "action": 0,
                    "phase": context_phase,
                    "effective_threshold": float(self.risk_threshold),
                    "volatility_regime": self._compute_volatility_regime(
                        self._current_volatility
                    ),
                    "lyapunov_stable": self._lyapunov_value <= 0,
                    "stress_mode": self.stress_mode.value,
                },
            )
            return 0

        # Apply Kalman filter
        filtered_signal = self.kalman_filter_signal(float(signal_strength))

        # Apply compensatory modulation with bounds
        adjusted_signal = filtered_signal * self.compensatory_factor

        # Bound the adjusted signal for numerical stability
        adjusted_signal = max(-SIGNAL_BOUND_MAX, min(SIGNAL_BOUND_MAX, adjusted_signal))

        # Get current volatility regime
        volatility_regime = self._compute_volatility_regime(self._current_volatility)

        # Apply risk aversion to threshold during high volatility
        effective_threshold = self._apply_risk_aversion(self.risk_threshold)

        # Lyapunov stability check: be more conservative if system unstable
        if self._lyapunov_value > 0 and len(self._fe_history) > 5:
            # System showing instability - increase threshold for safety
            effective_threshold *= INSTABILITY_PENALTY

        reason_codes: list[str] = []

        # Decision with threshold check
        if abs(adjusted_signal) > effective_threshold:
            action_candidate = int(np.sign(adjusted_signal))
        else:
            action_candidate = 0
            reason_codes.append("below_threshold")

        if volatility_regime == "extreme":
            action_candidate = 0
            reason_codes.append("extreme_volatility_hold")

        if self.chronic_counter > self.chronic_threshold * 2:
            action_candidate = 0
            reason_codes.append("chronic_stress_hold")

        # Crisis-mode safety guard
        if self.stress_mode == StressMode.CRISIS:
            crisis_reason = {
                "stress_level": float(self.stress_level),
                "threshold": float(effective_threshold),
                "mode": self.stress_mode.value,
                "action_before_guard": action_candidate,
                "crisis_action_mode": self.crisis_action_mode,
            }
            if self.crisis_action_mode == "hold":
                action_candidate = 0
                reason_codes.append("crisis_hold")
            elif self.crisis_action_mode == "reduce_only":
                action_candidate = -1 if adjusted_signal < -effective_threshold else 0
                crisis_reason["reduce_only_applied"] = True
                if action_candidate == 0:
                    reason_codes.append("crisis_reduce_only_block")
            self.log_action("Crisis guard", crisis_reason)

        # Conformal prediction gate (last safety filter)
        q = self._compute_conformal_q()
        conformal_ready = len(self._calibration_scores) >= self.min_calibration
        interval: tuple[float, float] | None = None
        confidence_gate_pass = True

        if self.conformal_gate_enabled:
            if not conformal_ready or not np.isfinite(q):
                action_candidate = 0
                confidence_gate_pass = False
                reason_codes.append("conformal_not_ready")
            else:
                interval = (float(adjusted_signal - q), float(adjusted_signal + q))
                assert q >= 0, "conformal_q must be non-negative"
                confidence_gate_pass = not (interval[0] <= 0.0 <= interval[1])
                if not confidence_gate_pass:
                    action_candidate = 0
                    reason_codes.append("conformal_reject")
        else:
            conformal_ready = False
            confidence_gate_pass = True
            reason_codes.append("conformal_disabled")

        action = action_candidate
        if not confidence_gate_pass:
            assert action == 0, "Action must be HOLD when confidence gate fails"
        if not conformal_ready and self.conformal_gate_enabled:
            assert action == 0, "Action must be HOLD when conformal calibration is not ready"

        self._last_conformal_q = float(q)
        self._last_prediction_interval = interval
        self._last_conformal_ready = bool(conformal_ready)
        self._last_confidence_gate_pass = bool(confidence_gate_pass)

        self.log_action(
            "Decision",
            {
                "raw_signal": float(signal_strength),
                "filtered_signal": float(filtered_signal),
                "adjusted_signal": float(adjusted_signal),
                "action": action,
                "conformal_q": self._last_conformal_q,
                "prediction_interval": self._last_prediction_interval,
                "conformal_ready": conformal_ready,
                "confidence_gate_pass": confidence_gate_pass,
                "reason_codes": reason_codes,
                "phase": context_phase,
                "effective_threshold": float(effective_threshold),
                "volatility_regime": volatility_regime,
                "lyapunov_stable": self._lyapunov_value <= 0,
                "stress_mode": self.stress_mode.value,
            },
        )

        return action

    def _canonical_json(self, payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _next_timestamp(self) -> str:
        timestamp = self._time_provider()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if self._last_timestamp and timestamp < self._last_timestamp:
            timestamp = self._last_timestamp
        self._last_timestamp = timestamp
        return timestamp.isoformat().replace("+00:00", "Z")

    def _compute_decision_id(self, timestamp: str) -> str:
        payload = f"{timestamp}|{len(self.history)}|{self.stress_mode.value}|{self.risk_threshold}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log_action(self, action_type: str, details: dict) -> None:
        """Append tamper-evident audit trace event with stable schema."""

        timestamp = self._next_timestamp()
        params_snapshot = {
            "action_threshold": float(self.risk_threshold),
            "smoothing_alpha": float(self.smoothing_alpha),
            "stress_threshold": float(self.stress_threshold),
            "crisis_threshold": float(self.crisis_threshold),
            "alpha": float(self.alpha),
            "calibration_window": int(self.calibration_window),
            "min_calibration": int(self.min_calibration),
            "conformal_gate_enabled": bool(self.conformal_gate_enabled),
            "stress_q_multiplier": float(self._stress_q_multiplier),
            "crisis_q_multiplier": float(self._crisis_q_multiplier),
        }

        conformal_q = float(details.get("conformal_q", self._last_conformal_q))
        prediction_interval = details.get("prediction_interval", self._last_prediction_interval)
        prediction_interval_low = (
            float(prediction_interval[0]) if prediction_interval else float("nan")
        )
        prediction_interval_high = (
            float(prediction_interval[1]) if prediction_interval else float("nan")
        )

        event_without_hash = {
            "timestamp_utc": timestamp,
            "schema_version": TRACE_SCHEMA_VERSION,
            "decision_id": self._compute_decision_id(timestamp),
            "prev_hash": self._last_event_hash,
            "mode": self.stress_mode.value,
            "stress_level": float(self.stress_level),
            "chronic_counter": int(self.chronic_counter),
            "free_energy_proxy": float(self.free_energy_proxy),
            "raw_signal": float(details.get("raw_signal", np.nan)),
            "filtered_signal": float(details.get("filtered_signal", np.nan)),
            "adjusted_signal": float(details.get("adjusted_signal", np.nan)),
            "conformal_q": float(conformal_q),
            "prediction_interval_low": prediction_interval_low,
            "prediction_interval_high": prediction_interval_high,
            "conformal_ready": bool(details.get("conformal_ready", self._last_conformal_ready)),
            "action": int(details.get("action", 0)),
            "confidence_gate_pass": bool(
                details.get("confidence_gate_pass", self._last_confidence_gate_pass)
            ),
            "reason_codes": list(details.get("reason_codes", [])) + [action_type],
            "params_snapshot": params_snapshot,
            "mode_context": details.get("mode", self.stress_mode.value),
            "stress_level_context": float(details.get("stress_level", self.stress_level)),
        }

        event_json = self._canonical_json(event_without_hash)
        event_hash = hashlib.sha256(
            (event_without_hash["prev_hash"] + event_json).encode("utf-8")
        ).hexdigest()

        event = {**event_without_hash, "event_hash": event_hash}
        self.history.append(event)
        self._last_event_hash = event_hash

    def get_trace(self) -> pd.DataFrame:
        """Export trace history as DataFrame with stable schema."""

        return pd.DataFrame(self.history)

    def export_trace_jsonl(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for event in self.history:
                f.write(self._canonical_json(event) + "\n")

    def export_trace_dataframe(self) -> pd.DataFrame:
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

    def get_stability_metrics(self) -> StabilityMetrics:
        """Get extended stability metrics for monitoring.

        Returns:
            StabilityMetrics with mathematical stability indicators
        """
        volatility_regime = self._compute_volatility_regime(self._current_volatility)

        # Compute stability margin: how far from instability threshold
        # Requires minimum history for meaningful variance
        if len(self._fe_history) >= 10:
            recent_fe_variance = float(np.var(self._fe_history[-10:]))
            stability_margin = 1.0 / (1.0 + recent_fe_variance)
        elif len(self._fe_history) >= 2:
            # Use available history but note reduced confidence
            recent_fe_variance = float(np.var(self._fe_history))
            # Scale margin by history coverage (0-1 range)
            coverage = len(self._fe_history) / 10.0
            raw_margin = 1.0 / (1.0 + recent_fe_variance)
            stability_margin = raw_margin * coverage + 1.0 * (1.0 - coverage)
        else:
            stability_margin = 1.0

        return StabilityMetrics(
            monotonicity_violations=self._monotonicity_violations,
            gradient_clipping_events=self._gradient_clipping_events,
            lyapunov_value=float(self._lyapunov_value),
            stability_margin=float(stability_margin),
            volatility_regime=volatility_regime,
            risk_aversion_active=self._risk_aversion_active,
        )

    def is_stable(self) -> bool:
        """Check if the regulator is in a stable state.

        Uses Lyapunov-like stability criterion: system is stable if
        the Lyapunov value is non-positive (energy decreasing).

        Returns:
            True if system is stable, False otherwise
        """
        # Check Lyapunov condition - positive indicates energy increasing
        if self._lyapunov_value > FE_STABILITY_EPSILON:
            return False

        # Check volatility regime - extreme volatility is always unstable
        regime = self._compute_volatility_regime(self._current_volatility)
        if regime == "extreme":
            return False

        # Check recent stability margin
        if len(self._fe_history) >= 10:
            recent_fe_variance = float(np.var(self._fe_history[-10:]))
            if recent_fe_variance > FE_VARIANCE_THRESHOLD:
                return False

        return True

    def reset(self) -> None:
        """Reset regulator state to initial conditions."""
        self.stress_level = 0.0
        self.free_energy_proxy = 0.0
        self.chronic_counter = 0
        self.history.clear()
        self._last_event_hash = TRACE_EMPTY_HASH
        self._last_timestamp = None
        self.kalman_state = 0.0
        self.kalman_variance = 1.0

        # Reset enhanced stability tracking
        self._monotonicity_violations = 0
        self._gradient_clipping_events = 0
        self._fe_history.clear()
        self._volatility_history.clear()
        self._lyapunov_value = 0.0
        self._current_volatility = 0.0
        self._risk_aversion_active = False
        self._feedback_gain = 0.1

        # Reset conformal calibration
        self._calibration_scores.clear()
        self._coverage_events = 0
        self._coverage_hits = 0
        self._last_conformal_q = float("nan")
        self._last_prediction_interval = None
        self._last_conformal_ready = False
        self._last_confidence_gate_pass = False


__all__ = [
    "ECSInspiredRegulator",
    "ECSMetrics",
    "StabilityMetrics",
    "StressMode",
    "GRADIENT_BOUND_MAX",
    "GRADIENT_BOUND_MIN",
    "FE_STABILITY_EPSILON",
    "VOLATILITY_SPIKE_THRESHOLD",
    "RISK_AVERSION_MULTIPLIER",
    "FE_DECAY_FACTOR",
    "SIGNAL_BOUND_MAX",
    "INSTABILITY_PENALTY",
    "FE_VARIANCE_THRESHOLD",
    "RECOVERY_SMOOTHING_FACTOR",
    "TRACE_SCHEMA_VERSION",
    "TRACE_SCHEMA_FIELDS",
]
