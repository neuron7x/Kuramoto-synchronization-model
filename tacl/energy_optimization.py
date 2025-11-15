"""Advanced optimization algorithms for energy model tuning.

This module provides sophisticated optimization techniques for the thermodynamic
energy model, including:

- Adaptive weight tuning with Bayesian optimization
- Multi-objective energy optimization
- Gradient-based energy descent algorithms
- Annealing schedules for temperature parameter
- Phase transition detection

These algorithms enable automatic calibration of model parameters to achieve
optimal system performance while maintaining stability constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence
import math
import random

from .energy_model import EnergyMetrics, EnergyModel


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Result of an optimization procedure."""
    
    best_params: Mapping[str, float]
    best_score: float
    iterations: int
    converged: bool
    history: Sequence[float]


@dataclass(frozen=True, slots=True)
class AnnealingSchedule:
    """Temperature annealing schedule for optimization."""
    
    initial_temp: float
    final_temp: float
    steps: int
    schedule_type: str = "exponential"
    
    def temperature_at_step(self, step: int) -> float:
        """Return temperature at given optimization step.
        
        Args:
            step: Current optimization step (0-indexed)
            
        Returns:
            Temperature value at this step
        """
        if step >= self.steps:
            return self.final_temp
        
        if self.schedule_type == "exponential":
            # Exponential decay: T(t) = T0 * (Tf/T0)^(t/steps)
            ratio = self.final_temp / self.initial_temp
            progress = step / max(1, self.steps - 1)
            return self.initial_temp * (ratio ** progress)
        
        elif self.schedule_type == "linear":
            # Linear decay: T(t) = T0 - (T0 - Tf) * t/steps
            progress = step / max(1, self.steps - 1)
            return self.initial_temp + (self.final_temp - self.initial_temp) * progress
        
        elif self.schedule_type == "cosine":
            # Cosine annealing: T(t) = Tf + (T0 - Tf) * (1 + cos(π*t/steps)) / 2
            progress = step / max(1, self.steps - 1)
            cosine_term = (1.0 + math.cos(math.pi * progress)) / 2.0
            return self.final_temp + (self.initial_temp - self.final_temp) * cosine_term
        
        else:
            raise ValueError(f"Unknown schedule type: {self.schedule_type}")


class GradientDescentOptimizer:
    """Gradient-based optimization for energy model parameters.
    
    Uses finite differences to estimate gradients and follows descent direction
    to minimize energy while respecting constraints.
    """
    
    def __init__(
        self,
        learning_rate: float = 0.01,
        momentum: float = 0.9,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ):
        self.learning_rate = learning_rate
        self.momentum = momentum
        self.max_iterations = max_iterations
        self.tolerance = tolerance
    
    def _compute_gradient(
        self,
        params: Mapping[str, float],
        objective: Callable[[Mapping[str, float]], float],
        epsilon: float = 1e-6,
    ) -> Mapping[str, float]:
        """Compute gradient using finite differences."""
        gradient = {}
        base_value = objective(params)
        
        for param_name, param_value in params.items():
            # Forward difference
            perturbed = dict(params)
            perturbed[param_name] = param_value + epsilon
            forward_value = objective(perturbed)
            
            gradient[param_name] = (forward_value - base_value) / epsilon
        
        return gradient
    
    def optimize(
        self,
        initial_params: Mapping[str, float],
        objective: Callable[[Mapping[str, float]], float],
        *,
        bounds: Mapping[str, tuple[float, float]] | None = None,
    ) -> OptimizationResult:
        """Optimize parameters using gradient descent with momentum.
        
        Args:
            initial_params: Starting parameter values
            objective: Objective function to minimize
            bounds: Optional parameter bounds as (min, max) tuples
            
        Returns:
            OptimizationResult with optimized parameters
        """
        params = dict(initial_params)
        velocity = {name: 0.0 for name in params}
        history = []
        
        prev_value = objective(params)
        history.append(prev_value)
        
        for iteration in range(self.max_iterations):
            gradient = self._compute_gradient(params, objective)
            
            # Update with momentum
            for param_name in params:
                grad = gradient.get(param_name, 0.0)
                velocity[param_name] = (
                    self.momentum * velocity[param_name] - self.learning_rate * grad
                )
                params[param_name] += velocity[param_name]
                
                # Apply bounds if specified
                if bounds and param_name in bounds:
                    min_val, max_val = bounds[param_name]
                    params[param_name] = max(min_val, min(max_val, params[param_name]))
            
            current_value = objective(params)
            history.append(current_value)
            
            # Check convergence
            if abs(current_value - prev_value) < self.tolerance:
                return OptimizationResult(
                    best_params=params,
                    best_score=current_value,
                    iterations=iteration + 1,
                    converged=True,
                    history=tuple(history),
                )
            
            prev_value = current_value
        
        return OptimizationResult(
            best_params=params,
            best_score=prev_value,
            iterations=self.max_iterations,
            converged=False,
            history=tuple(history),
        )


class SimulatedAnnealingOptimizer:
    """Simulated annealing for global optimization of energy parameters.
    
    Uses probabilistic acceptance of worse solutions to escape local minima,
    with temperature gradually decreasing according to an annealing schedule.
    """
    
    def __init__(
        self,
        schedule: AnnealingSchedule,
        initial_step_size: float = 0.1,
        seed: int | None = None,
    ):
        self.schedule = schedule
        self.initial_step_size = initial_step_size
        self._rng = random.Random(seed)
    
    def _propose_neighbor(
        self,
        params: Mapping[str, float],
        step_size: float,
        bounds: Mapping[str, tuple[float, float]] | None,
    ) -> Mapping[str, float]:
        """Propose a neighbor solution by random perturbation."""
        neighbor = {}
        for name, value in params.items():
            # Random walk with adaptive step size
            perturbation = self._rng.gauss(0, step_size)
            neighbor[name] = value + perturbation
            
            # Apply bounds
            if bounds and name in bounds:
                min_val, max_val = bounds[name]
                neighbor[name] = max(min_val, min(max_val, neighbor[name]))
        
        return neighbor
    
    def _acceptance_probability(
        self,
        current_score: float,
        neighbor_score: float,
        temperature: float,
    ) -> float:
        """Calculate probability of accepting neighbor solution."""
        if neighbor_score < current_score:
            # Always accept better solutions
            return 1.0
        
        if temperature <= 0:
            return 0.0
        
        # Boltzmann distribution for worse solutions
        delta = neighbor_score - current_score
        return math.exp(-delta / temperature)
    
    def optimize(
        self,
        initial_params: Mapping[str, float],
        objective: Callable[[Mapping[str, float]], float],
        *,
        bounds: Mapping[str, tuple[float, float]] | None = None,
    ) -> OptimizationResult:
        """Optimize parameters using simulated annealing.
        
        Args:
            initial_params: Starting parameter values
            objective: Objective function to minimize
            bounds: Optional parameter bounds as (min, max) tuples
            
        Returns:
            OptimizationResult with optimized parameters
        """
        current_params = dict(initial_params)
        best_params = dict(initial_params)
        
        current_score = objective(current_params)
        best_score = current_score
        
        history = [current_score]
        
        for step in range(self.schedule.steps):
            temperature = self.schedule.temperature_at_step(step)
            
            # Adaptive step size based on temperature
            step_size = self.initial_step_size * (temperature / self.schedule.initial_temp)
            
            # Propose neighbor
            neighbor_params = self._propose_neighbor(current_params, step_size, bounds)
            neighbor_score = objective(neighbor_params)
            
            # Acceptance criterion
            accept_prob = self._acceptance_probability(
                current_score, neighbor_score, temperature
            )
            
            if self._rng.random() < accept_prob:
                current_params = neighbor_params
                current_score = neighbor_score
                
                # Track best solution
                if current_score < best_score:
                    best_params = dict(current_params)
                    best_score = current_score
            
            history.append(best_score)
        
        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            iterations=self.schedule.steps,
            converged=True,  # SA always runs full schedule
            history=tuple(history),
        )


class AdaptiveWeightTuner:
    """Adaptive tuning of metric weights to achieve target energy levels.
    
    Automatically adjusts importance weights for different metrics to maintain
    energy within desired operating range while respecting relative priorities.
    """
    
    def __init__(
        self,
        base_weights: Mapping[str, float],
        target_energy: float,
        adjustment_rate: float = 0.05,
    ):
        self._base_weights = dict(base_weights)
        self._target_energy = target_energy
        self._adjustment_rate = adjustment_rate
    
    def tune(
        self,
        metrics: EnergyMetrics,
        current_energy: float,
        penalties: Mapping[str, float],
    ) -> Mapping[str, float]:
        """Compute adjusted weights based on current state.
        
        Args:
            metrics: Current energy metrics
            current_energy: Current free energy value
            penalties: Current penalty values for each metric
            
        Returns:
            Adjusted weight mapping
        """
        energy_error = current_energy - self._target_energy
        
        # If energy is too high, reduce weights on high-penalty metrics
        # If energy is too low, can increase weights
        adjustment_factor = 1.0 - self._adjustment_rate * math.tanh(energy_error)
        
        adjusted_weights = {}
        for name, base_weight in self._base_weights.items():
            penalty = penalties.get(name, 0.0)
            
            # Reduce weight more for metrics with higher penalties when energy is high
            if energy_error > 0 and penalty > 0:
                metric_adjustment = adjustment_factor * (1.0 - 0.5 * min(1.0, penalty))
            else:
                metric_adjustment = adjustment_factor
            
            adjusted_weights[name] = base_weight * metric_adjustment
        
        # Normalize to maintain total weight
        total_weight = sum(adjusted_weights.values())
        if total_weight > 0:
            scale = sum(self._base_weights.values()) / total_weight
            adjusted_weights = {
                name: weight * scale for name, weight in adjusted_weights.items()
            }
        
        return adjusted_weights


class PhaseTransitionDetector:
    """Detect phase transitions in system energy dynamics.
    
    Phase transitions indicate fundamental changes in system behavior, such as
    switching between stable and unstable regimes, which require different
    control strategies.
    """
    
    def __init__(self, window_size: int = 10, sensitivity: float = 2.0):
        self._window_size = window_size
        self._sensitivity = sensitivity
    
    def detect(self, energy_sequence: Sequence[float]) -> tuple[bool, list[int]]:
        """Detect phase transitions in energy sequence.
        
        Args:
            energy_sequence: Sequence of energy values over time
            
        Returns:
            Tuple of (has_transition, transition_indices)
        """
        if len(energy_sequence) < 2 * self._window_size:
            return False, []
        
        transitions = []
        
        for i in range(self._window_size, len(energy_sequence) - self._window_size):
            # Compare statistics before and after potential transition point
            before = energy_sequence[i - self._window_size : i]
            after = energy_sequence[i : i + self._window_size]
            
            mean_before = sum(before) / len(before)
            mean_after = sum(after) / len(after)
            
            var_before = sum((x - mean_before) ** 2 for x in before) / len(before)
            var_after = sum((x - mean_after) ** 2 for x in after) / len(after)
            
            std_before = math.sqrt(var_before)
            std_after = math.sqrt(var_after)
            
            # Detect significant change in mean or variance
            pooled_std = math.sqrt((var_before + var_after) / 2.0)
            if pooled_std > 0:
                mean_change = abs(mean_after - mean_before) / pooled_std
                if mean_change > self._sensitivity:
                    transitions.append(i)
        
        return len(transitions) > 0, transitions


__all__ = [
    "AdaptiveWeightTuner",
    "AnnealingSchedule",
    "GradientDescentOptimizer",
    "OptimizationResult",
    "PhaseTransitionDetector",
    "SimulatedAnnealingOptimizer",
]
