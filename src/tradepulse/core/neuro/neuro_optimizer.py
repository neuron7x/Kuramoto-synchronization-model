"""Cross-Neuromodulator Optimization Loop.

This module implements a holistic optimization system that coordinates multiple
neuromodulators (dopamine, serotonin, GABA, NA/ACh) to achieve balanced and
optimal trading performance. It ensures neuromodulator interactions maintain
homeostatic balance while maximizing risk-adjusted returns.

The optimizer implements:
- Multi-objective optimization across neuromodulators
- Homeostatic balance constraints
- Adaptive learning rates based on market regimes
- Synaptic plasticity optimization
- Real-time performance monitoring

Public API
----------
NeuroOptimizer : Main optimization controller
OptimizationConfig : Configuration for optimization parameters
BalanceMetrics : Neuromodulator balance health metrics
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class OptimizationConfig:
    """Configuration for neuromodulator optimization.

    Attributes
    ----------
    balance_weight : float
        Weight for homeostatic balance objective (0-1)
    performance_weight : float
        Weight for performance objective (0-1)
    stability_weight : float
        Weight for stability objective (0-1)
    learning_rate : float
        Base learning rate for parameter updates
    learning_rate_floor : float
        Minimum adaptive learning rate when plateauing
    adaptive_decay : float
        Multiplicative decay factor applied when improvements stall
    plateau_patience : int
        Number of stagnant iterations before applying decay
    ema_alpha : float
        Smoothing factor for exponential moving average of the objective
    max_gradient_norm : float
        Maximum relative gradient magnitude applied per update
    momentum : float
        Momentum factor for gradient updates
    max_iterations : int
        Maximum optimization iterations per session
    convergence_threshold : float
        Convergence threshold for early stopping
    enable_plasticity : bool
        Enable synaptic plasticity optimization
    plasticity_window : int
        Window for plasticity calculations
    regime_adaptation : bool
        Enable market regime-based adaptation
    """

    balance_weight: float = 0.35
    performance_weight: float = 0.45
    stability_weight: float = 0.20
    learning_rate: float = 0.01
    learning_rate_floor: float = 0.001
    adaptive_decay: float = 0.6
    plateau_patience: int = 5
    ema_alpha: float = 0.2
    max_gradient_norm: float = 0.05
    momentum: float = 0.9
    max_iterations: int = 100
    convergence_threshold: float = 0.001
    enable_plasticity: bool = True
    plasticity_window: int = 50
    regime_adaptation: bool = True

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not np.isclose(
            self.balance_weight + self.performance_weight + self.stability_weight, 1.0
        ):
            raise ValueError("Objective weights must sum to 1.0")

        if not 0 < self.learning_rate < 1:
            raise ValueError("Learning rate must be in (0, 1)")

        if not 0 < self.learning_rate_floor <= self.learning_rate:
            raise ValueError("Learning rate floor must be in (0, learning_rate]")

        if not 0 < self.adaptive_decay < 1:
            raise ValueError("Adaptive decay must be in (0, 1)")

        if self.plateau_patience < 1:
            raise ValueError("Plateau patience must be positive")

        if not 0 < self.ema_alpha <= 1:
            raise ValueError("EMA alpha must be in (0, 1]")

        if not 0 < self.max_gradient_norm <= 1:
            raise ValueError("Max gradient norm must be in (0, 1]")

        if not 0 <= self.momentum < 1:
            raise ValueError("Momentum must be in [0, 1)")


@dataclass
class BalanceMetrics:
    """Neuromodulator balance health metrics.

    Attributes
    ----------
    dopamine_serotonin_ratio : float
        Ratio of dopamine to serotonin levels
    gaba_excitation_balance : float
        Balance between inhibition and excitation
    arousal_attention_coherence : float
        Coherence between arousal and attention
    overall_balance_score : float
        Composite balance score (0-1, higher is better)
    homeostatic_deviation : float
        Deviation from homeostatic setpoint
    """

    dopamine_serotonin_ratio: float
    gaba_excitation_balance: float
    arousal_attention_coherence: float
    overall_balance_score: float
    homeostatic_deviation: float


class NeuroOptimizer:
    """Cross-neuromodulator optimization system.

    This optimizer coordinates multiple neuromodulators to achieve optimal
    performance while maintaining homeostatic balance. It uses gradient-based
    optimization with momentum and adaptive learning rates.

    Parameters
    ----------
    config : OptimizationConfig
        Optimization configuration
    logger : Optional[Callable[[str, float], None]]
        Optional logging callback for metrics
    """

    def __init__(
        self,
        config: OptimizationConfig,
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        """Initialize the neuro-optimizer."""
        self.config = config
        self._logger = logger or (lambda name, value: None)

        # Optimization state
        self._velocity: Dict[str, Dict[str, float]] = {}
        self._current_lr = self.config.learning_rate
        self._iteration = 0
        self._best_objective = -np.inf
        self._last_improvement = 0
        self._convergence_history: List[float] = []
        self._plateau_steps = 0
        self._ema_objective: Optional[float] = None

        # Homeostatic setpoints
        self._setpoints = self._initialize_setpoints()

        # Performance tracking
        self._performance_history: List[float] = []
        self._balance_history: List[BalanceMetrics] = []

    def _initialize_setpoints(self) -> Dict[str, float]:
        """Initialize homeostatic setpoints for each neuromodulator.

        Returns
        -------
        Dict[str, float]
            Setpoint values for homeostatic regulation
        """
        return {
            "dopamine_level": 0.5,  # Baseline dopamine
            "serotonin_level": 0.3,  # Baseline serotonin (lower = less stress)
            "gaba_inhibition": 0.4,  # Moderate inhibition
            "na_arousal": 1.0,  # Neutral arousal
            "ach_attention": 0.7,  # Good attention
            # Ratios and balances
            "da_5ht_ratio": 1.67,  # Dopamine/serotonin ratio
            "excitation_inhibition": 1.5,  # E/I balance
        }

    def optimize(
        self,
        current_params: Dict[str, Any],
        current_state: Dict[str, float],
        performance_score: float,
    ) -> Tuple[Dict[str, Any], BalanceMetrics]:
        """Execute optimization iteration.

        Parameters
        ----------
        current_params : Dict[str, Any]
            Current neuromodulator parameters
        current_state : Dict[str, float]
            Current neuromodulator state (levels, ratios, etc.)
        performance_score : float
            Current performance metric (higher is better)

        Returns
        -------
        Tuple[Dict[str, Any], BalanceMetrics]
            Updated parameters and balance metrics
        """
        # Calculate balance metrics
        balance = self._calculate_balance_metrics(current_state)
        self._balance_history.append(balance)

        # Calculate composite objective
        objective = self._calculate_objective(performance_score, balance, current_state)
        self._performance_history.append(objective)
        self._update_learning_rate(objective)

        # Update best
        if objective > self._best_objective:
            self._best_objective = objective
            self._last_improvement = self._iteration

        # Calculate gradients (approximated via finite differences)
        gradients = self._estimate_gradients(
            current_params, current_state, performance_score
        )

        # Apply updates with momentum
        updated_params = self._apply_updates(current_params, gradients)

        # Log metrics
        self._log_metrics(objective, balance)

        self._iteration += 1

        return updated_params, balance

    def _calculate_balance_metrics(self, state: Dict[str, float]) -> BalanceMetrics:
        """Calculate neuromodulator balance metrics.

        Parameters
        ----------
        state : Dict[str, float]
            Current neuromodulator state

        Returns
        -------
        BalanceMetrics
            Computed balance metrics
        """
        # Extract state values with defaults
        da_level = state.get("dopamine_level", 0.5)
        sero_level = state.get("serotonin_level", 0.3)
        gaba_inhib = state.get("gaba_inhibition", 0.4)
        arousal = state.get("na_arousal", 1.0)
        attention = state.get("ach_attention", 0.7)

        # Calculate ratios
        da_5ht_ratio = da_level / (sero_level + 1e-6)

        # Excitation-inhibition balance (higher dopamine = more excitation)
        excitation = da_level + arousal
        inhibition = gaba_inhib + sero_level
        ei_balance = excitation / (inhibition + 1e-6)

        # Arousal-attention coherence (should be correlated)
        aa_coherence = 1.0 - abs(arousal - attention) / 2.0

        # Calculate deviations from setpoints
        da_5ht_dev = (
            abs(da_5ht_ratio - self._setpoints["da_5ht_ratio"])
            / self._setpoints["da_5ht_ratio"]
        )
        ei_dev = (
            abs(ei_balance - self._setpoints["excitation_inhibition"])
            / self._setpoints["excitation_inhibition"]
        )

        # Overall homeostatic deviation
        homeostatic_dev = (da_5ht_dev + ei_dev) / 2.0

        # Overall balance score (inverse of deviation)
        balance_score = 1.0 / (1.0 + homeostatic_dev)

        return BalanceMetrics(
            dopamine_serotonin_ratio=da_5ht_ratio,
            gaba_excitation_balance=ei_balance,
            arousal_attention_coherence=aa_coherence,
            overall_balance_score=balance_score,
            homeostatic_deviation=homeostatic_dev,
        )

    def _calculate_objective(
        self,
        performance: float,
        balance: BalanceMetrics,
        state: Dict[str, float],
    ) -> float:
        """Calculate multi-objective optimization target.

        Parameters
        ----------
        performance : float
            Performance score
        balance : BalanceMetrics
            Balance metrics
        state : Dict[str, float]
            Current state

        Returns
        -------
        float
            Composite objective value (higher is better)
        """
        # Normalize performance to [0, 1] with configurable Sharpe bounds
        # Typical Sharpe ranges: [-2, 3] but can be adjusted
        sharpe_min, sharpe_max = -2.0, 3.0
        perf_normalized = np.clip(
            (performance - sharpe_min) / (sharpe_max - sharpe_min), 0, 1
        )

        # Balance objective (already in [0, 1])
        balance_obj = balance.overall_balance_score

        # Stability objective (variance over recent history)
        if len(self._performance_history) > 10:
            recent_perf = self._performance_history[-10:]
            stability = 1.0 - np.std(recent_perf) / (np.mean(recent_perf) + 1e-6)
            stability = np.clip(stability, 0, 1)
        else:
            stability = 0.5  # Neutral until we have history

        # Weighted combination
        objective = (
            self.config.performance_weight * perf_normalized
            + self.config.balance_weight * balance_obj
            + self.config.stability_weight * stability
        )

        return objective

    def _estimate_gradients(
        self,
        params: Dict[str, Any],
        state: Dict[str, float],
        performance: float,
    ) -> Dict[str, Dict[str, float]]:
        """Estimate gradients using finite differences.

        This is a placeholder for actual gradient estimation. In production,
        this would use more sophisticated techniques like evolutionary strategies
        or Bayesian optimization.

        Parameters
        ----------
        params : Dict[str, Any]
            Current parameters
        state : Dict[str, float]
            Current state
        performance : float
            Current performance

        Returns
        -------
        Dict[str, Dict[str, float]]
            Estimated gradients for each parameter
        """
        gradients = {}

        # For each neuromodulator
        for module in ["dopamine", "serotonin", "gaba", "na_ach"]:
            if module not in params:
                continue

            gradients[module] = {}

            # For each parameter in the module
            for param_name, param_value in params[module].items():
                if not isinstance(param_value, (int, float)):
                    continue

                # Estimate gradient based on homeostatic deviation
                # This encourages parameters that restore balance
                # Use exact module name matching to avoid substring issues
                balance = self._balance_history[-1] if self._balance_history else None
                if balance:
                    # Push parameters toward homeostatic setpoints
                    if (
                        module == "dopamine"
                        and balance.dopamine_serotonin_ratio
                        < self._setpoints["da_5ht_ratio"]
                    ):
                        grad = 1.0  # Increase dopamine params
                    elif (
                        module == "serotonin"
                        and balance.dopamine_serotonin_ratio
                        > self._setpoints["da_5ht_ratio"]
                    ):
                        grad = 1.0  # Increase serotonin params
                    else:
                        grad = 0.0  # No change needed
                else:
                    grad = 0.0

                gradients[module][param_name] = grad * self._current_lr

        return gradients

    def _apply_updates(
        self,
        params: Dict[str, Any],
        gradients: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """Apply parameter updates with momentum.

        Parameters
        ----------
        params : Dict[str, Any]
            Current parameters
        gradients : Dict[str, Dict[str, float]]
            Estimated gradients

        Returns
        -------
        Dict[str, Any]
            Updated parameters
        """
        updated = {}

        for module, module_params in params.items():
            if module not in gradients:
                updated[module] = module_params
                continue

            updated[module] = {}
            module_grads = gradients[module]

            # Initialize velocity for this module if needed
            if module not in self._velocity:
                self._velocity[module] = {}

            for param_name, param_value in module_params.items():
                if param_name not in module_grads:
                    updated[module][param_name] = param_value
                    continue

                # Initialize velocity for this parameter if needed
                if param_name not in self._velocity[module]:
                    self._velocity[module][param_name] = 0.0

                # Momentum update
                velocity = (
                    self.config.momentum * self._velocity[module][param_name]
                    + module_grads[param_name]
                )
                self._velocity[module][param_name] = velocity

                # Gradient clipping relative to parameter magnitude
                max_step = abs(param_value) * self.config.max_gradient_norm
                clipped_velocity = float(np.clip(velocity, -max_step, max_step))

                # Apply update
                new_value = param_value + clipped_velocity

                # Clip to reasonable bounds (prevent instability)
                new_value = np.clip(new_value, param_value * 0.8, param_value * 1.2)

                updated[module][param_name] = new_value

        return updated

    def _update_learning_rate(self, objective: float) -> None:
        """Adapt learning rate based on progress and stability."""

        if self._ema_objective is None:
            self._ema_objective = objective
        else:
            self._ema_objective = (
                self.config.ema_alpha * objective
                + (1 - self.config.ema_alpha) * self._ema_objective
            )

        improving = objective >= self._ema_objective
        if improving:
            self._plateau_steps = 0
            # Gradually recover toward base learning rate after decay events
            recovery_step = (self.config.learning_rate - self._current_lr) * 0.25
            self._current_lr = min(
                self.config.learning_rate, self._current_lr + recovery_step
            )
            return

        self._plateau_steps += 1
        if self._plateau_steps >= self.config.plateau_patience:
            decayed_lr = self._current_lr * self.config.adaptive_decay
            self._current_lr = max(self.config.learning_rate_floor, decayed_lr)
            self._plateau_steps = 0
            # Reset velocity to avoid stale momentum during plateaus
            self._velocity = {}

    def _log_metrics(self, objective: float, balance: BalanceMetrics) -> None:
        """Log optimization metrics.

        Parameters
        ----------
        objective : float
            Current objective value
        balance : BalanceMetrics
            Current balance metrics
        """
        self._logger("neuro_opt.objective", objective)
        self._logger("neuro_opt.balance_score", balance.overall_balance_score)
        self._logger("neuro_opt.homeostatic_dev", balance.homeostatic_deviation)
        self._logger("neuro_opt.da_5ht_ratio", balance.dopamine_serotonin_ratio)
        self._logger("neuro_opt.ei_balance", balance.gaba_excitation_balance)
        self._logger("neuro_opt.aa_coherence", balance.arousal_attention_coherence)

    def get_optimization_report(self) -> Dict[str, Any]:
        """Generate optimization status report.

        Returns
        -------
        Dict[str, Any]
            Comprehensive optimization report
        """
        if not self._performance_history:
            return {
                "status": "no_data",
                "message": "No optimization data available",
            }

        recent_perf = self._performance_history[-10:]
        recent_balance = self._balance_history[-10:]

        return {
            "status": "active",
            "iteration": self._iteration,
            "best_objective": self._best_objective,
            "current_objective": self._performance_history[-1],
            "performance_trend": (
                "improving"
                if len(recent_perf) > 1 and recent_perf[-1] > recent_perf[0]
                else "stable"
            ),
            "avg_balance_score": np.mean(
                [b.overall_balance_score for b in recent_balance]
            ),
            "avg_homeostatic_dev": np.mean(
                [b.homeostatic_deviation for b in recent_balance]
            ),
            "convergence": self._check_convergence(),
            "health_status": self._assess_health(
                recent_balance[-1] if recent_balance else None
            ),
        }

    def _check_convergence(self) -> Dict[str, Any]:
        """Check if optimization has converged.

        Returns
        -------
        Dict[str, Any]
            Convergence status information
        """
        if len(self._performance_history) < 20:
            return {
                "converged": False,
                "reason": "insufficient_data",
            }

        recent = self._performance_history[-20:]
        variance = np.std(recent)

        if variance < self.config.convergence_threshold:
            return {
                "converged": True,
                "variance": variance,
                "message": "Optimization has converged",
            }
        else:
            return {
                "converged": False,
                "variance": variance,
                "message": f"Still optimizing (variance={variance:.4f})",
            }

    def _assess_health(self, balance: Optional[BalanceMetrics]) -> Dict[str, Any]:
        """Assess neuromodulator system health.

        Parameters
        ----------
        balance : Optional[BalanceMetrics]
            Latest balance metrics

        Returns
        -------
        Dict[str, Any]
            Health assessment
        """
        if balance is None:
            return {
                "status": "unknown",
                "message": "No balance data available",
            }

        issues = []

        # Check DA/5-HT ratio
        if balance.dopamine_serotonin_ratio < 1.0:
            issues.append("Low dopamine/serotonin ratio - system may be over-stressed")
        elif balance.dopamine_serotonin_ratio > 3.0:
            issues.append("High dopamine/serotonin ratio - excessive risk-taking")

        # Check E/I balance
        if balance.gaba_excitation_balance < 1.0:
            issues.append("Excessive inhibition - may miss opportunities")
        elif balance.gaba_excitation_balance > 2.5:
            issues.append("Excessive excitation - impulsive behavior risk")

        # Check arousal-attention coherence
        if balance.arousal_attention_coherence < 0.5:
            issues.append("Poor arousal-attention coherence - attention deficits")

        # Overall assessment
        if balance.overall_balance_score > 0.8:
            status = "healthy"
            message = "Neuromodulator system is well-balanced"
        elif balance.overall_balance_score > 0.6:
            status = "acceptable"
            message = "Minor imbalances detected but within acceptable range"
        else:
            status = "warning"
            message = "Significant imbalances detected - intervention recommended"

        return {
            "status": status,
            "message": message,
            "balance_score": balance.overall_balance_score,
            "homeostatic_deviation": balance.homeostatic_deviation,
            "issues": issues if issues else ["No issues detected"],
        }

    def reset(self) -> None:
        """Reset optimizer state."""
        self._velocity = {}
        self._iteration = 0
        self._best_objective = -np.inf
        self._convergence_history = []
        self._performance_history = []
        self._balance_history = []
