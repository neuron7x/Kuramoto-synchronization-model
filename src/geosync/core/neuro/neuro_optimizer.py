# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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
NumericConfig : Numeric tuning for optimization calculations
BalanceMetrics : Neuromodulator balance health metrics

Documentation references
------------------------
See the neuro-optimization guide for formulas and bounds:
- docs/neuro_optimization_guide.md#cross-neuromodulator-optimizer
- docs/neuro_optimization_guide.md#homeostatic-deviation--balance-score
- docs/neuro_optimization_guide.md#numerical-stability
- docs/neuro_optimization_guide.md#optimizationconfig
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from geosync.core.neuro._validation import BoundsSpec


@dataclass
class NumericConfig:
    """Numeric configuration for optimization calculations.

    Attributes
    ----------
    performance_min : float
        Minimum performance value for normalization
    performance_max : float
        Maximum performance value for normalization
    stability_epsilon : float
        Numerical stability constant for ratio/stability denominators
    gradient_dev_clip : float
        Maximum absolute deviation used in proportional gradient estimates
    max_gradient_norm : float
        Maximum relative gradient magnitude applied per update
    da_5ht_ratio_range : Tuple[float, float]
        Acceptable dopamine/serotonin ratio range for health checks
    ei_balance_range : Tuple[float, float]
        Acceptable excitation/inhibition balance range for health checks
    aa_coherence_min : float
        Minimum arousal-attention coherence for health checks
    """

    performance_min: float = -2.0
    performance_max: float = 3.0
    stability_epsilon: float = 1e-6
    gradient_dev_clip: float = 3.0
    max_gradient_norm: float = 0.05
    da_5ht_ratio_range: Tuple[float, float] = (1.0, 3.0)
    ei_balance_range: Tuple[float, float] = (1.0, 2.5)
    aa_coherence_min: float = 0.5

    def __post_init__(self) -> None:
        if self.performance_min >= self.performance_max:
            raise ValueError("performance_min must be less than performance_max")

        if not 0 < self.max_gradient_norm <= 1:
            raise ValueError("Max gradient norm must be in (0, 1]")

        if self.stability_epsilon <= 0:
            raise ValueError("stability_epsilon must be positive")

        if self.gradient_dev_clip <= 0:
            raise ValueError("gradient_dev_clip must be positive")

        self._validate_range(self.da_5ht_ratio_range, "da_5ht_ratio_range")
        self._validate_range(self.ei_balance_range, "ei_balance_range")
        self._validate_aa_coherence_min()

    @staticmethod
    def _validate_range(value_range: Tuple[float, float], name: str) -> None:
        if len(value_range) != 2 or not all(
            isinstance(value, (int, float)) for value in value_range
        ):
            raise ValueError(f"{name} must be a tuple of two numbers")
        low, high = value_range
        if low <= 0 or high <= 0 or low >= high:
            raise ValueError(f"{name} must be positive with low < high")

    def _validate_aa_coherence_min(self) -> None:
        if not isinstance(self.aa_coherence_min, (int, float)):
            raise ValueError("aa_coherence_min must be a number")
        if not 0 <= self.aa_coherence_min <= 1:
            raise ValueError("aa_coherence_min must be in [0, 1]")


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
    momentum : float
        Momentum factor for gradient updates
    max_iterations : int
        Maximum optimization iterations per session
    convergence_threshold : float
        Convergence threshold for early stopping
    history_window : int
        Window length for performance history tracking
    dtype : str
        Floating point dtype for numerical buffers (e.g., "float32")
    use_gpu : bool
        Whether to attempt a CuPy-backed execution path (optional)
    enable_plasticity : bool
        Enable synaptic plasticity optimization
    plasticity_window : int
        Window for plasticity calculations
    regime_adaptation : bool
        Enable market regime-based adaptation
    numeric : NumericConfig
        Numeric configuration for optimization calculations
    gradient_clip : Optional[float]
        Maximum absolute deviation used in proportional gradient estimates
    bounds_spec : Dict[str, Dict[str, BoundsSpec]]
        Structured parameter bounds with enforcement behavior
    param_bounds : Dict[str, Dict[str, Tuple[float, float]]]
        Optional parameter bounds by module and parameter name
    """

    balance_weight: float = 0.35
    performance_weight: float = 0.45
    stability_weight: float = 0.20
    learning_rate: float = 0.01
    learning_rate_floor: float = 0.001
    adaptive_decay: float = 0.6
    plateau_patience: int = 5
    ema_alpha: float = 0.2
    momentum: float = 0.9
    max_iterations: int = 100
    convergence_threshold: float = 0.001
    history_window: int = 10
    dtype: str = "float32"
    use_gpu: bool = False
    enable_plasticity: bool = True
    plasticity_window: int = 50
    regime_adaptation: bool = True
    numeric: NumericConfig = field(default_factory=NumericConfig)
    gradient_clip: Optional[float] = None
    bounds_spec: Dict[str, Dict[str, BoundsSpec]] = field(default_factory=dict)
    param_bounds: Dict[str, Dict[str, Tuple[float, float]]] = field(default_factory=dict)

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

        if not 0 <= self.momentum < 1:
            raise ValueError("Momentum must be in [0, 1)")

        if self.history_window < 1:
            raise ValueError("History window must be a positive integer")

        if not isinstance(self.numeric, NumericConfig):
            raise ValueError("numeric must be a NumericConfig instance")

        if self.gradient_clip is None:
            self.gradient_clip = self.numeric.gradient_dev_clip
        elif self.gradient_clip <= 0:
            raise ValueError("gradient_clip must be positive")

        self._validate_bounds_spec()
        self._validate_param_bounds()

        try:
            np.dtype(self.dtype)
        except TypeError as exc:
            raise ValueError(f"Invalid dtype supplied: {self.dtype}") from exc

    @property
    def da_5ht_ratio_range(self) -> Tuple[float, float]:
        """Expose DA/5-HT ratio bounds from the numeric configuration."""
        return self.numeric.da_5ht_ratio_range

    @property
    def ei_balance_range(self) -> Tuple[float, float]:
        """Expose excitation/inhibition bounds from the numeric configuration."""
        return self.numeric.ei_balance_range

    def _validate_param_bounds(self) -> None:
        if not isinstance(self.param_bounds, dict):
            raise ValueError("param_bounds must be a dict")
        for module, module_bounds in self.param_bounds.items():
            if not isinstance(module_bounds, dict):
                raise ValueError(f"param_bounds[{module!r}] must be a dict")
            for param_name, bounds in module_bounds.items():
                if (
                    not isinstance(bounds, tuple)
                    or len(bounds) != 2
                    or not all(isinstance(value, (int, float)) for value in bounds)
                ):
                    raise ValueError(
                        f"param_bounds[{module!r}][{param_name!r}] must be a tuple of two numbers"
                    )
                low, high = bounds
                if low >= high:
                    raise ValueError(
                        f"param_bounds[{module!r}][{param_name!r}] must have low < high"
                    )

    def _validate_bounds_spec(self) -> None:
        if not isinstance(self.bounds_spec, dict):
            raise ValueError("bounds_spec must be a dict")
        for module, module_bounds in self.bounds_spec.items():
            if not isinstance(module_bounds, dict):
                raise ValueError(f"bounds_spec[{module!r}] must be a dict")
            for param_name, spec in module_bounds.items():
                if not isinstance(spec, BoundsSpec):
                    raise ValueError(
                        f"bounds_spec[{module!r}][{param_name!r}] must be a BoundsSpec"
                    )
                if spec.min_value >= spec.max_value:
                    raise ValueError(
                        f"bounds_spec[{module!r}][{param_name!r}] must have min_value < max_value"
                    )
                if spec.behavior not in {"clip", "raise"}:
                    raise ValueError(
                        f"bounds_spec[{module!r}][{param_name!r}] must have behavior "
                        "set to 'clip' or 'raise'"
                    )


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

    DRIFT_WINDOW = 10
    DRIFT_MEAN_THRESHOLD = 0.05
    DRIFT_MEDIAN_THRESHOLD = 0.05

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
        self._dtype = np.dtype(self.config.dtype)
        self._xp = self._select_array_module()

        # Performance tracking
        self._performance_history: List[float] = []
        self._balance_history: List[BalanceMetrics] = []
        self._param_history: List[Dict[str, Dict[str, float]]] = []

    def _select_array_module(self):
        """Select numpy or an optional CuPy backend."""
        if not self.config.use_gpu:
            return np
        try:
            import cupy as cp

            return cp
        except ImportError:
            return np

    def _to_array(self, values: List[float]):
        """Create a contiguous buffer with the configured dtype."""
        return self._xp.asarray(values, dtype=self._dtype, order="C")

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
        if len(self._performance_history) > self.config.history_window:
            self._performance_history = self._performance_history[-self.config.history_window :]
        self._update_learning_rate(objective)

        # Update best
        if objective > self._best_objective:
            self._best_objective = objective
            self._last_improvement = self._iteration

        # Calculate gradients (approximated via finite differences)
        gradients = self._estimate_gradients(current_params, current_state, performance_score)

        # Apply updates with momentum
        updated_params = self._apply_updates(current_params, gradients)
        self._param_history.append(self._snapshot_params(updated_params))

        # Log metrics
        self._log_metrics(objective, balance)

        self._iteration += 1

        return updated_params, balance

    def _snapshot_params(self, params: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Capture a numeric-only snapshot of parameters for drift tracking."""
        snapshot: Dict[str, Dict[str, float]] = {}
        for module, module_params in params.items():
            if not isinstance(module_params, dict):
                continue
            numeric_params = {
                name: float(value)
                for name, value in module_params.items()
                if isinstance(value, (int, float))
            }
            if numeric_params:
                snapshot[module] = numeric_params
        return snapshot

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
        da_level, sero_level, gaba_inhib, arousal, attention = self._to_array(
            [
                state.get("dopamine_level", 0.5),
                state.get("serotonin_level", 0.3),
                state.get("gaba_inhibition", 0.4),
                state.get("na_arousal", 1.0),
                state.get("ach_attention", 0.7),
            ]
        )

        # Calculate ratios
        epsilon = self._dtype.type(self.config.numeric.stability_epsilon)
        da_5ht_ratio = da_level / (sero_level + epsilon)

        # Excitation-inhibition balance (higher dopamine = more excitation)
        excitation = da_level + arousal
        inhibition = gaba_inhib + sero_level
        ei_balance = excitation / (inhibition + epsilon)

        da_min, da_max = self.config.numeric.da_5ht_ratio_range
        da_5ht_ratio = self._xp.clip(da_5ht_ratio, da_min, da_max)

        ei_min, ei_max = self.config.numeric.ei_balance_range
        ei_balance = self._xp.clip(ei_balance, ei_min, ei_max)

        # Arousal-attention coherence (should be correlated)
        aa_coherence = self._dtype.type(1.0) - self._xp.abs(arousal - attention) / self._dtype.type(
            2.0
        )
        aa_coherence = self._xp.clip(aa_coherence, 0.0, 1.0)

        # Calculate deviations from setpoints
        da_5ht_dev = self._xp.abs(da_5ht_ratio - self._setpoints["da_5ht_ratio"]) / (
            self._setpoints["da_5ht_ratio"] + epsilon
        )
        ei_dev = self._xp.abs(ei_balance - self._setpoints["excitation_inhibition"]) / (
            self._setpoints["excitation_inhibition"] + epsilon
        )

        # Overall homeostatic deviation.
        # Formula reference: docs/neuro_optimization_guide.md ("Homeostatic Deviation & Balance Score").
        homeostatic_dev = (da_5ht_dev + ei_dev) / self._dtype.type(2.0)
        homeostatic_dev = self._xp.clip(homeostatic_dev, self._dtype.type(0.0), self._xp.inf)

        # Overall balance score (inverse of deviation).
        # Formula reference: docs/neuro_optimization_guide.md ("Homeostatic Deviation & Balance Score").
        balance_score = self._dtype.type(1.0) / (self._dtype.type(1.0) + homeostatic_dev)
        balance_score = self._xp.clip(balance_score, self._dtype.type(0.0), self._dtype.type(1.0))

        return BalanceMetrics(
            dopamine_serotonin_ratio=float(da_5ht_ratio),
            gaba_excitation_balance=float(ei_balance),
            arousal_attention_coherence=float(aa_coherence),
            overall_balance_score=float(balance_score),
            homeostatic_deviation=float(homeostatic_dev),
        )

    def _calculate_objective(
        self,
        performance: float,
        balance: BalanceMetrics,
        state: Dict[str, float],
    ) -> float:
        """Calculate multi-objective optimization target.

        Metric scales and weighting
        ----------------------------
        - Performance is normalized from a Sharpe ratio range of [-2, 3] into [0, 1]
          with clipping. Values below -2 map to 0, above 3 map to 1.
        - Balance is the homeostatic balance score already in [0, 1] (higher is better).
        - Stability is derived from the inverse coefficient of variation over recent
          objective history, clipped to [0, 1]. Before enough history exists, a
          neutral value of 0.5 is used.
        The final objective is a linear combination of these scaled metrics using
        the configured weights (performance_weight, balance_weight, stability_weight).

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
        # Normalize performance to [0, 1] with configurable Sharpe bounds.
        # Formula reference: docs/neuro_optimization_guide.md ("Metric Scales and Objective Influence").
        sharpe_min, sharpe_max = (
            self.config.numeric.performance_min,
            self.config.numeric.performance_max,
        )
        perf_normalized = float(
            self._xp.clip(
                (performance - sharpe_min) / (sharpe_max - sharpe_min),
                0,
                1,
            )
        )

        # Balance objective (already in [0, 1])
        balance_obj = balance.overall_balance_score

        # Stability objective (variance over recent history).
        # Formula reference: docs/neuro_optimization_guide.md ("Stability Objective").
        if len(self._performance_history) >= self.config.history_window > 1:
            recent_perf = self._performance_history[-self.config.history_window :]
            recent_array = self._xp.asarray(recent_perf, dtype=self._dtype)
            mean_perf = self._xp.mean(recent_array)
            std_perf = self._xp.std(recent_array)
            epsilon = self._dtype.type(self.config.numeric.stability_epsilon)
            denom = self._xp.maximum(self._xp.abs(mean_perf), epsilon)
            stability = self._dtype.type(1.0) - std_perf / denom
            stability = float(self._xp.clip(stability, 0, 1))
        else:
            stability = 0.5  # Neutral until we have history

        # Weighted combination
        # Formal objective definition: docs/neuro_optimization_guide.md ("Formal Objective")
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
        epsilon = self._dtype.type(self.config.numeric.stability_epsilon)

        # Proportional gradient heuristic.
        # Formula reference: docs/neuro_optimization_guide.md ("Proportional Gradient Heuristic").
        def relative_deviation(value: float, setpoint: float) -> float:
            return float((value - setpoint) / (setpoint + epsilon))

        max_deviation = self._dtype.type(self.config.gradient_clip)

        def clip_deviation(value: float) -> float:
            return float(self._xp.clip(value, -max_deviation, max_deviation))

        dopamine_level = float(state.get("dopamine_level", self._setpoints["dopamine_level"]))
        serotonin_level = float(state.get("serotonin_level", self._setpoints["serotonin_level"]))
        ratio_value = dopamine_level / (serotonin_level + float(epsilon))
        ratio_deviation = clip_deviation(
            relative_deviation(ratio_value, self._setpoints["da_5ht_ratio"])
        )

        gaba_value = float(state.get("gaba_inhibition", self._setpoints["gaba_inhibition"]))
        arousal_value = float(state.get("na_arousal", self._setpoints["na_arousal"]))
        attention_value = float(state.get("ach_attention", self._setpoints["ach_attention"]))

        gaba_dev = clip_deviation(
            relative_deviation(gaba_value, self._setpoints["gaba_inhibition"])
        )
        arousal_dev = clip_deviation(
            relative_deviation(arousal_value, self._setpoints["na_arousal"])
        )
        attention_dev = clip_deviation(
            relative_deviation(attention_value, self._setpoints["ach_attention"])
        )

        # For each neuromodulator
        for module in ["dopamine", "serotonin", "gaba", "na_ach"]:
            if module not in params:
                continue

            gradients[module] = {}

            # For each parameter in the module
            for param_name, param_value in params[module].items():
                if not isinstance(param_value, (int, float)):
                    continue

                # Estimate gradient based on proportional deviation from setpoints.
                if module == "dopamine":
                    grad = -ratio_deviation
                elif module == "serotonin":
                    grad = ratio_deviation
                elif module == "gaba":
                    grad = -gaba_dev
                else:
                    if "arousal" in param_name:
                        grad = -arousal_dev
                    elif "attention" in param_name:
                        grad = -attention_dev
                    else:
                        grad = -0.5 * (arousal_dev + attention_dev)

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
                max_step = abs(param_value) * self.config.numeric.max_gradient_norm
                clipped_velocity = float(self._xp.clip(velocity, -max_step, max_step))

                # Apply update
                new_value = param_value + clipped_velocity

                # Clip to reasonable bounds (prevent instability)
                new_value = float(self._xp.clip(new_value, param_value * 0.8, param_value * 1.2))

                bounds_spec = self.config.bounds_spec.get(module, {}).get(param_name)
                if bounds_spec is not None:
                    if bounds_spec.behavior == "clip":
                        new_value = float(
                            self._xp.clip(new_value, bounds_spec.min_value, bounds_spec.max_value)
                        )
                    elif new_value < bounds_spec.min_value or new_value > bounds_spec.max_value:
                        raise ValueError(
                            f"{module}.{param_name} must be between "
                            f"{bounds_spec.min_value} and {bounds_spec.max_value}"
                        )
                else:
                    # Apply config bounds for safety (legacy)
                    bounds = self.config.param_bounds.get(module, {}).get(param_name)
                    if bounds is not None:
                        new_value = float(self._xp.clip(new_value, bounds[0], bounds[1]))

                updated[module][param_name] = new_value

        return updated

    def _update_learning_rate(self, objective: float) -> None:
        """Adapt learning rate based on progress and stability."""

        if self._ema_objective is None:
            self._ema_objective = objective
        else:
            # EMA update: ema_t = alpha * objective_t + (1 - alpha) * ema_{t-1}
            self._ema_objective = (
                self.config.ema_alpha * objective
                + (1 - self.config.ema_alpha) * self._ema_objective
            )

        # Improvement rule: objective_t >= ema_t
        improving = objective >= self._ema_objective
        if improving:
            self._plateau_steps = 0
            # Recovery: lr_t = min(lr_base, lr_prev + 0.25 * (lr_base - lr_prev))
            recovery_step = (self.config.learning_rate - self._current_lr) * 0.25
            self._current_lr = min(self.config.learning_rate, self._current_lr + recovery_step)
            return

        # Plateau tracking: apply decay once plateau_steps >= plateau_patience
        self._plateau_steps += 1
        if self._plateau_steps >= self.config.plateau_patience:
            # Decay: lr_t = max(lr_floor, lr_prev * adaptive_decay)
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
        prefix = "neuro_opt"
        metrics = {
            "objective": objective,
            "balance_score": balance.overall_balance_score,
            "homeostatic_dev": balance.homeostatic_deviation,
            "da_5ht_ratio": balance.dopamine_serotonin_ratio,
            "ei_balance": balance.gaba_excitation_balance,
            "aa_coherence": balance.arousal_attention_coherence,
        }
        for name, value in metrics.items():
            self._logger(f"{prefix}.{name}", value)

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
        parameter_drift = self._calculate_parameter_drift(self.DRIFT_WINDOW)

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
            "parameter_drift": parameter_drift,
            "avg_balance_score": float(
                self._xp.mean(self._xp.asarray([b.overall_balance_score for b in recent_balance]))
            ),
            "avg_homeostatic_dev": float(
                self._xp.mean(self._xp.asarray([b.homeostatic_deviation for b in recent_balance]))
            ),
            "convergence": self._check_convergence(),
            "health_status": self._assess_health(
                recent_balance[-1] if recent_balance else None,
                drift_stats=parameter_drift,
            ),
        }

    def _calculate_parameter_drift(self, window: int) -> Dict[str, Any]:
        """Calculate mean/median parameter deltas over the last N steps."""
        if len(self._param_history) < 2:
            return {"window": 0, "stats": {}}

        window = min(window, len(self._param_history) - 1)
        recent = self._param_history[-(window + 1) :]
        drift_values: Dict[str, Dict[str, List[float]]] = {}

        for prev, curr in zip(recent[:-1], recent[1:]):
            for module, curr_params in curr.items():
                prev_params = prev.get(module)
                if not prev_params:
                    continue
                for name, value in curr_params.items():
                    if name not in prev_params:
                        continue
                    drift_values.setdefault(module, {}).setdefault(name, []).append(
                        abs(value - prev_params[name])
                    )

        drift_stats: Dict[str, Dict[str, Dict[str, float]]] = {}
        for module, module_params in drift_values.items():
            module_stats: Dict[str, Dict[str, float]] = {}
            for name, deltas in module_params.items():
                if not deltas:
                    continue
                module_stats[name] = {
                    "mean_delta": float(self._xp.mean(self._xp.asarray(deltas))),
                    "median_delta": float(self._xp.median(self._xp.asarray(deltas))),
                }
            if module_stats:
                drift_stats[module] = module_stats

        return {"window": window, "stats": drift_stats}

    def _check_convergence(self) -> Dict[str, Any]:
        """Check if optimization has converged.

        Returns
        -------
        Dict[str, Any]
            Convergence status information
        """
        if len(self._performance_history) < self.config.history_window:
            return {
                "converged": False,
                "reason": "insufficient_data",
            }

        recent = self._performance_history[-self.config.history_window :]
        variance = float(self._xp.std(self._xp.asarray(recent)))

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

    def _assess_health(
        self,
        balance: Optional[BalanceMetrics],
        drift_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
        drift_risk = {
            "status": "unknown",
            "thresholds": {
                "mean_delta": self.DRIFT_MEAN_THRESHOLD,
                "median_delta": self.DRIFT_MEDIAN_THRESHOLD,
            },
            "violations": [],
            "max_mean_delta": 0.0,
            "max_median_delta": 0.0,
        }

        da_ratio_min, da_ratio_max = self.config.da_5ht_ratio_range
        ei_min, ei_max = self.config.ei_balance_range

        # Check DA/5-HT ratio
        if balance.dopamine_serotonin_ratio < da_ratio_min:
            issues.append("Low dopamine/serotonin ratio - system may be over-stressed")
        elif balance.dopamine_serotonin_ratio > da_ratio_max:
            issues.append("High dopamine/serotonin ratio - excessive risk-taking")

        # Check E/I balance
        if balance.gaba_excitation_balance < ei_min:
            issues.append("Excessive inhibition - may miss opportunities")
        elif balance.gaba_excitation_balance > ei_max:
            issues.append("Excessive excitation - impulsive behavior risk")

        # Check arousal-attention coherence
        if balance.arousal_attention_coherence < self.config.numeric.aa_coherence_min:
            issues.append("Poor arousal-attention coherence - attention deficits")

        if drift_stats and drift_stats.get("stats"):
            violations = []
            max_mean = 0.0
            max_median = 0.0
            for module, module_params in drift_stats["stats"].items():
                for name, stats in module_params.items():
                    mean_delta = stats.get("mean_delta", 0.0)
                    median_delta = stats.get("median_delta", 0.0)
                    max_mean = max(max_mean, mean_delta)
                    max_median = max(max_median, median_delta)
                    if (
                        mean_delta >= self.DRIFT_MEAN_THRESHOLD
                        or median_delta >= self.DRIFT_MEDIAN_THRESHOLD
                    ):
                        violations.append(f"{module}.{name}")

            drift_risk.update(
                {
                    "status": "warning" if violations else "stable",
                    "violations": violations,
                    "max_mean_delta": max_mean,
                    "max_median_delta": max_median,
                }
            )
            if violations:
                issues.append("Parameter drift risk detected: " + ", ".join(sorted(violations)))
        else:
            drift_risk["status"] = "unknown"

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
            "drift_risk": drift_risk,
        }

    def reset(self) -> None:
        """Reset optimizer state."""
        self._velocity = {}
        self._iteration = 0
        self._best_objective = -np.inf
        self._convergence_history = []
        self._performance_history = []
        self._balance_history = []
        self._param_history = []
