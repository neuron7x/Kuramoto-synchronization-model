"""Adaptive Neuromodulator Calibration System.

This module implements an adaptive calibration system that optimizes neuromodulator
parameters based on real-time performance metrics and market conditions. It enables
the neuroscience-grounded AI system to self-tune for optimal decision-making.

The calibrator uses a multi-objective optimization approach balancing:
- Risk-adjusted returns (Sharpe ratio)
- Drawdown minimization
- Trade execution efficiency
- Neuromodulator balance stability

Public API
----------
AdaptiveCalibrator : Main calibration controller
CalibrationMetrics : Performance metrics for calibration
CalibrationState : Internal state tracking
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class CalibrationMetrics:
    """Performance metrics for neuromodulator calibration.

    Attributes
    ----------
    sharpe_ratio : float
        Risk-adjusted returns metric
    max_drawdown : float
        Maximum drawdown observed (0-1)
    win_rate : float
        Proportion of winning trades (0-1)
    avg_hold_time : float
        Average position hold time in steps
    dopamine_stability : float
        Variance metric for dopamine levels (lower is better)
    serotonin_stress : float
        Average serotonin stress level (0-1)
    gaba_inhibition_rate : float
        Proportion of trades inhibited by GABA (0-1)
    na_ach_arousal : float
        Average arousal level (0-2)
    total_trades : int
        Total number of trades executed
    timestamp : float
        Unix timestamp of metrics
    """

    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_hold_time: float
    dopamine_stability: float
    serotonin_stress: float
    gaba_inhibition_rate: float
    na_ach_arousal: float
    total_trades: int
    timestamp: float

    def composite_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """Calculate weighted composite performance score.

        Parameters
        ----------
        weights : Optional[Dict[str, float]]
            Custom weights for each metric. Defaults to balanced weights.

        Returns
        -------
        float
            Composite score (higher is better)
        """
        if weights is None:
            weights = {
                'sharpe': 0.30,
                'drawdown': 0.25,
                'win_rate': 0.15,
                'stability': 0.15,
                'stress': 0.10,
                'arousal': 0.05,
            }

        # Normalize and combine metrics
        score = (
            weights['sharpe'] * np.clip(self.sharpe_ratio / 3.0, 0, 1)
            + weights['drawdown'] * (1 - self.max_drawdown)
            + weights['win_rate'] * self.win_rate
            + weights['stability'] * (1 - np.clip(self.dopamine_stability / 0.5, 0, 1))
            + weights['stress'] * (1 - self.serotonin_stress)
            + weights['arousal'] * np.clip(self.na_ach_arousal / 2.0, 0, 1)
        )
        return score


@dataclass
class CalibrationState:
    """Internal state for adaptive calibration.

    Attributes
    ----------
    current_params : Dict[str, Any]
        Current neuromodulator parameters
    best_params : Dict[str, Any]
        Best parameters found so far
    best_score : float
        Best composite score achieved
    iteration : int
        Current calibration iteration
    temperature : float
        Exploration temperature (simulated annealing)
    last_improvement : int
        Iteration of last improvement
    metrics_history : List[CalibrationMetrics]
        Historical performance metrics
    """

    current_params: Dict[str, Any]
    best_params: Dict[str, Any]
    best_score: float
    iteration: int
    temperature: float
    last_improvement: int
    metrics_history: List[CalibrationMetrics]


class AdaptiveCalibrator:
    """Adaptive calibration system for neuromodulator parameters.

    This class implements a gradient-free optimization algorithm that adapts
    neuromodulator parameters based on observed performance. It uses a combination
    of simulated annealing and Bayesian optimization principles.

    The calibrator operates in two modes:
    1. Exploration: Widely sample parameter space when performance is suboptimal
    2. Exploitation: Fine-tune parameters around best configurations

    Parameters
    ----------
    initial_params : Dict[str, Any]
        Initial neuromodulator parameters
    temperature_initial : float, optional
        Initial exploration temperature, by default 1.0
    temperature_decay : float, optional
        Temperature decay rate per iteration, by default 0.95
    min_temperature : float, optional
        Minimum temperature floor, by default 0.01
    patience : int, optional
        Iterations without improvement before reset, by default 50
    perturbation_scale : float, optional
        Scale of parameter perturbations, by default 0.1
    """

    def __init__(
        self,
        initial_params: Dict[str, Any],
        *,
        temperature_initial: float = 1.0,
        temperature_decay: float = 0.95,
        min_temperature: float = 0.01,
        patience: int = 50,
        perturbation_scale: float = 0.1,
    ) -> None:
        """Initialize the adaptive calibrator."""
        self._validate_params(initial_params)

        self.state = CalibrationState(
            current_params=initial_params.copy(),
            best_params=initial_params.copy(),
            best_score=-np.inf,
            iteration=0,
            temperature=temperature_initial,
            last_improvement=0,
            metrics_history=[],
        )

        self.temperature_initial = temperature_initial
        self.temperature_decay = temperature_decay
        self.min_temperature = min_temperature
        self.patience = patience
        self.perturbation_scale = perturbation_scale

        # Parameter bounds for each neuromodulator
        self.param_bounds = self._initialize_bounds()

    def _validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameter structure."""
        required_keys = {'dopamine', 'serotonin', 'gaba', 'na_ach'}
        if not required_keys.issubset(params.keys()):
            missing = required_keys - set(params.keys())
            raise ValueError(f"Missing required neuromodulator configs: {missing}")

    def _initialize_bounds(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """Initialize parameter bounds for safe exploration.

        Returns
        -------
        Dict[str, Dict[str, Tuple[float, float]]]
            Nested dictionary of (min, max) bounds for each parameter
        """
        return {
            'dopamine': {
                'discount_gamma': (0.90, 0.999),
                'learning_rate': (0.001, 0.05),
                'burst_factor': (1.0, 3.0),
                'base_temperature': (0.3, 2.0),
                'invigoration_threshold': (0.4, 0.8),
            },
            'serotonin': {
                'stress_threshold': (0.1, 0.3),
                'release_threshold': (0.05, 0.2),
                'desensitization_rate': (0.001, 0.02),
                'floor_min': (0.1, 0.5),
            },
            'gaba': {
                'k_inhibit': (0.2, 0.8),
                'impulse_threshold': (0.3, 0.7),
                'stdp_lr': (0.001, 0.02),
                'max_inhibition': (0.5, 0.95),
            },
            'na_ach': {
                'arousal_gain': (0.8, 2.0),
                'attention_gain': (0.5, 1.5),
                'risk_min': (0.3, 0.7),
                'risk_max': (1.2, 2.0),
            },
        }

    def step(self, metrics: CalibrationMetrics) -> Dict[str, Any]:
        """Execute one calibration step with new performance metrics.

        Parameters
        ----------
        metrics : CalibrationMetrics
            Current performance metrics

        Returns
        -------
        Dict[str, Any]
            Updated neuromodulator parameters to try next
        """
        # Store metrics
        self.state.metrics_history.append(metrics)

        # Calculate composite score
        score = metrics.composite_score()

        # Update best if improved
        if score > self.state.best_score:
            self.state.best_score = score
            self.state.best_params = self.state.current_params.copy()
            self.state.last_improvement = self.state.iteration

        # Check if we should reset (stuck in local optimum)
        if self.state.iteration - self.state.last_improvement > self.patience:
            self._reset_exploration()

        # Generate new candidate parameters
        candidate_params = self._generate_candidate()

        # Accept or reject based on score difference (simulated annealing)
        delta = score - self._get_previous_score()
        # Clip delta/temperature to prevent overflow in exp()
        accept_prob = np.exp(np.clip(delta / self.state.temperature, -20, 0)) if delta < 0 else 1.0

        if np.random.random() < accept_prob:
            self.state.current_params = candidate_params

        # Decay temperature
        self.state.temperature = max(
            self.min_temperature,
            self.state.temperature * self.temperature_decay
        )

        self.state.iteration += 1

        return self.state.current_params.copy()

    def _get_previous_score(self) -> float:
        """Get the most recent composite score."""
        if len(self.state.metrics_history) < 2:
            return -np.inf
        return self.state.metrics_history[-2].composite_score()

    def _generate_candidate(self) -> Dict[str, Any]:
        """Generate candidate parameters using current best + perturbation.

        Returns
        -------
        Dict[str, Any]
            Candidate parameter dictionary
        """
        # Start from best known parameters
        candidate = {}

        # Adaptive perturbation: larger when temperature is high (exploration)
        scale = self.perturbation_scale * self.state.temperature

        for module, params in self.state.best_params.items():
            if module not in self.param_bounds:
                # Non-neuromodulator params: pass through
                candidate[module] = params
                continue

            candidate[module] = {}
            bounds = self.param_bounds[module]

            for key, value in params.items():
                if key not in bounds:
                    # Unknown param: pass through
                    candidate[module][key] = value
                    continue

                min_val, max_val = bounds[key]

                # Use truncated normal for efficient sampling within bounds
                # Gaussian perturbation scaled to parameter range
                range_size = max_val - min_val
                perturbation = np.random.normal(0, scale * range_size)
                # Clip to stay within bounds
                new_value = np.clip(value + perturbation, min_val, max_val)
                candidate[module][key] = new_value

        return candidate

    def _reset_exploration(self) -> None:
        """Reset to high temperature for renewed exploration."""
        self.state.temperature = self.temperature_initial * 0.5
        self.state.last_improvement = self.state.iteration
        # Inject some randomness into current params
        self.state.current_params = self._generate_random_params()

    def _generate_random_params(self) -> Dict[str, Any]:
        """Generate random parameters within bounds.

        Returns
        -------
        Dict[str, Any]
            Randomly sampled parameter dictionary
        """
        random_params = {}

        for module, params in self.state.best_params.items():
            if module not in self.param_bounds:
                random_params[module] = params
                continue

            random_params[module] = {}
            bounds = self.param_bounds[module]

            for key, value in params.items():
                if key not in bounds:
                    random_params[module][key] = value
                    continue

                min_val, max_val = bounds[key]
                random_params[module][key] = np.random.uniform(min_val, max_val)

        return random_params

    def get_best_params(self) -> Dict[str, Any]:
        """Get the best parameters found so far.

        Returns
        -------
        Dict[str, Any]
            Best parameter configuration
        """
        return self.state.best_params.copy()

    def get_calibration_report(self) -> Dict[str, Any]:
        """Generate comprehensive calibration report.

        Returns
        -------
        Dict[str, Any]
            Report containing calibration statistics and recommendations
        """
        if not self.state.metrics_history:
            return {
                'status': 'no_data',
                'message': 'No calibration data available yet',
            }

        recent_metrics = self.state.metrics_history[-10:]

        return {
            'status': 'active',
            'iteration': self.state.iteration,
            'best_score': self.state.best_score,
            'current_temperature': self.state.temperature,
            'iterations_since_improvement': self.state.iteration - self.state.last_improvement,
            'best_params': self.state.best_params,
            'recent_performance': {
                'avg_sharpe': np.mean([m.sharpe_ratio for m in recent_metrics]),
                'avg_drawdown': np.mean([m.max_drawdown for m in recent_metrics]),
                'avg_win_rate': np.mean([m.win_rate for m in recent_metrics]),
                'dopamine_stability': np.mean([m.dopamine_stability for m in recent_metrics]),
            },
            'exploration_state': 'exploring' if self.state.temperature > 0.5 else 'exploiting',
            'recommendations': self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on calibration state.

        Returns
        -------
        List[str]
            List of recommendation strings
        """
        recommendations = []

        if not self.state.metrics_history:
            return ['Collect more performance data before generating recommendations']

        recent = self.state.metrics_history[-1]

        # High drawdown
        if recent.max_drawdown > 0.15:
            recommendations.append(
                "High drawdown detected. Consider increasing GABA inhibition "
                "and serotonin stress thresholds for more conservative trading."
            )

        # Low Sharpe
        if recent.sharpe_ratio < 0.5:
            recommendations.append(
                "Low Sharpe ratio. Consider adjusting dopamine learning rate "
                "or exploration temperature for better risk-adjusted returns."
            )

        # High stress
        if recent.serotonin_stress > 0.5:
            recommendations.append(
                "Elevated stress levels. Review serotonin desensitization parameters "
                "to prevent excessive hold periods."
            )

        # Unstable dopamine
        if recent.dopamine_stability > 0.4:
            recommendations.append(
                "High dopamine variance. Consider smoothing parameters or "
                "adjusting RPE calculation to stabilize decision-making."
            )

        # Good performance
        if recent.sharpe_ratio > 1.5 and recent.max_drawdown < 0.1:
            recommendations.append(
                "Excellent performance! Current parameters are well-tuned. "
                "Maintain current configuration and monitor for regime changes."
            )

        return recommendations if recommendations else [
            "Performance is within acceptable ranges. Continue monitoring."
        ]

    def export_state(self) -> Dict[str, Any]:
        """Export complete calibration state for persistence.

        Returns
        -------
        Dict[str, Any]
            Serializable state dictionary
        """
        return {
            'current_params': self.state.current_params,
            'best_params': self.state.best_params,
            'best_score': self.state.best_score,
            'iteration': self.state.iteration,
            'temperature': self.state.temperature,
            'last_improvement': self.state.last_improvement,
            'metrics_history': [asdict(m) for m in self.state.metrics_history],
            'config': {
                'temperature_initial': self.temperature_initial,
                'temperature_decay': self.temperature_decay,
                'min_temperature': self.min_temperature,
                'patience': self.patience,
                'perturbation_scale': self.perturbation_scale,
            },
        }

    @classmethod
    def from_state(cls, state_dict: Dict[str, Any]) -> AdaptiveCalibrator:
        """Restore calibrator from exported state.

        Parameters
        ----------
        state_dict : Dict[str, Any]
            State dictionary from export_state()

        Returns
        -------
        AdaptiveCalibrator
            Restored calibrator instance
        """
        config = state_dict['config']
        calibrator = cls(
            initial_params=state_dict['current_params'],
            temperature_initial=config['temperature_initial'],
            temperature_decay=config['temperature_decay'],
            min_temperature=config['min_temperature'],
            patience=config['patience'],
            perturbation_scale=config['perturbation_scale'],
        )

        # Restore internal state
        calibrator.state.best_params = state_dict['best_params']
        calibrator.state.best_score = state_dict['best_score']
        calibrator.state.iteration = state_dict['iteration']
        calibrator.state.temperature = state_dict['temperature']
        calibrator.state.last_improvement = state_dict['last_improvement']
        calibrator.state.metrics_history = [
            CalibrationMetrics(**m) for m in state_dict['metrics_history']
        ]

        return calibrator
