#!/usr/bin/env python3
"""Demonstration of energy optimization capabilities.

This script showcases advanced optimization algorithms for automatic tuning
of energy model parameters, including gradient descent, simulated annealing,
adaptive weight tuning, and phase transition detection.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tacl import (
    EnergyMetrics,
    EnergyModel,
    GradientDescentOptimizer,
    SimulatedAnnealingOptimizer,
    AnnealingSchedule,
    AdaptiveWeightTuner,
    PhaseTransitionDetector,
    DEFAULT_WEIGHTS,
    DEFAULT_THRESHOLDS,
)


def demo_gradient_descent():
    """Demonstrate gradient descent optimization."""
    print("=" * 70)
    print("GRADIENT DESCENT OPTIMIZATION")
    print("=" * 70)
    print()
    
    # Define objective: minimize difference from target energy
    target_energy = 1.2
    
    def objective(params):
        """Compute energy with given weight parameters."""
        weights = {
            "latency_p95": params["w_lat95"],
            "latency_p99": params["w_lat99"],
            "coherency_drift": params["w_drift"],
            "cpu_burn": 0.9,
            "mem_cost": 0.8,
            "queue_depth": 0.7,
            "packet_loss": 1.4,
        }
        
        model = EnergyModel(weights=weights, thresholds=DEFAULT_THRESHOLDS)
        
        # Test with sample metrics
        metrics = EnergyMetrics(
            latency_p95=75.0,
            latency_p99=105.0,
            coherency_drift=0.06,
            cpu_burn=0.65,
            mem_cost=5.5,
            queue_depth=28.0,
            packet_loss=0.003,
        )
        
        free_energy, _, _, _ = model.free_energy(metrics)
        
        # Objective: minimize squared error from target
        return (free_energy - target_energy) ** 2
    
    # Initial parameters
    initial_params = {
        "w_lat95": 1.6,
        "w_lat99": 1.9,
        "w_drift": 1.2,
    }
    
    print("Optimization Goal: Find weights that achieve target energy")
    print(f"Target energy: {target_energy:.6f}")
    print()
    print(f"Initial parameters: {initial_params}")
    print(f"Initial objective: {objective(initial_params):.6f}")
    print()
    
    # Run optimization
    optimizer = GradientDescentOptimizer(
        learning_rate=0.05,
        momentum=0.9,
        max_iterations=50,
        tolerance=1e-6,
    )
    
    result = optimizer.optimize(
        initial_params=initial_params,
        objective=objective,
        bounds={
            "w_lat95": (0.5, 3.0),
            "w_lat99": (0.5, 3.0),
            "w_drift": (0.5, 3.0),
        }
    )
    
    print(f"Optimization Results:")
    print(f"  Converged: {result.converged}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Best score: {result.best_score:.6f}")
    print(f"  Best parameters:")
    for name, value in result.best_params.items():
        print(f"    {name}: {value:.6f}")
    print()
    
    # Show convergence history
    print("Convergence history (first 10 and last 5):")
    history = list(result.history)
    for i, score in enumerate(history[:10]):
        print(f"  Iteration {i:2d}: {score:.6f}")
    if len(history) > 15:
        print("  ...")
        for i, score in enumerate(history[-5:], len(history) - 5):
            print(f"  Iteration {i:2d}: {score:.6f}")
    print()


def demo_simulated_annealing():
    """Demonstrate simulated annealing optimization."""
    print("=" * 70)
    print("SIMULATED ANNEALING OPTIMIZATION")
    print("=" * 70)
    print()
    
    # Define a multi-modal objective with local minima
    def objective(params):
        """Complex objective with multiple local minima."""
        x = params["x"]
        y = params["y"]
        
        # Rastrigin-like function with global minimum at (0, 0)
        return (
            20.0 
            + x ** 2 - 10.0 * ((2.0 * 3.14159 * x) ** 0.5).real
            + y ** 2 - 10.0 * ((2.0 * 3.14159 * y) ** 0.5).real
        )
    
    # Create annealing schedule
    schedule = AnnealingSchedule(
        initial_temp=2.0,
        final_temp=0.01,
        steps=300,
        schedule_type="exponential"
    )
    
    initial_params = {"x": 2.5, "y": -2.0}
    
    print("Optimization Goal: Find global minimum of multi-modal function")
    print(f"Initial parameters: {initial_params}")
    print(f"Initial objective: {objective(initial_params):.6f}")
    print()
    print(f"Annealing Schedule:")
    print(f"  Type: {schedule.schedule_type}")
    print(f"  Initial temp: {schedule.initial_temp:.2f}")
    print(f"  Final temp: {schedule.final_temp:.4f}")
    print(f"  Steps: {schedule.steps}")
    print()
    
    # Run optimization
    optimizer = SimulatedAnnealingOptimizer(
        schedule=schedule,
        initial_step_size=0.5,
        seed=42
    )
    
    result = optimizer.optimize(
        initial_params=initial_params,
        objective=objective,
        bounds={"x": (-5.0, 5.0), "y": (-5.0, 5.0)}
    )
    
    print(f"Optimization Results:")
    print(f"  Iterations: {result.iterations}")
    print(f"  Best score: {result.best_score:.6f}")
    print(f"  Best parameters:")
    for name, value in result.best_params.items():
        print(f"    {name}: {value:.6f}")
    print()
    
    # Temperature progression
    print("Temperature progression:")
    checkpoints = [0, 50, 100, 150, 200, 250, 299]
    for step in checkpoints:
        temp = schedule.temperature_at_step(step)
        print(f"  Step {step:3d}: T = {temp:.6f}")
    print()


def demo_adaptive_weight_tuning():
    """Demonstrate adaptive weight tuning."""
    print("=" * 70)
    print("ADAPTIVE WEIGHT TUNING")
    print("=" * 70)
    print()
    
    # Create tuner
    tuner = AdaptiveWeightTuner(
        base_weights=DEFAULT_WEIGHTS,
        target_energy=1.2,
        adjustment_rate=0.1,
    )
    
    model = EnergyModel(weights=DEFAULT_WEIGHTS)
    
    print(f"Tuning Goal: Maintain energy near {tuner._target_energy:.2f}")
    print(f"Adjustment rate: {tuner._adjustment_rate:.2f}")
    print()
    
    # Simulate scenario where energy drifts
    scenarios = [
        ("Normal load", 70.0),
        ("Increased load", 90.0),
        ("High load", 110.0),
        ("Peak load", 130.0),
    ]
    
    current_weights = dict(DEFAULT_WEIGHTS)
    
    for scenario_name, latency in scenarios:
        metrics = EnergyMetrics(
            latency_p95=latency,
            latency_p99=latency * 1.4,
            coherency_drift=0.05,
            cpu_burn=0.6 + (latency - 70) / 200.0,
            mem_cost=5.0 + (latency - 70) / 30.0,
            queue_depth=25.0 + (latency - 70) / 5.0,
            packet_loss=0.003,
        )
        
        # Evaluate with current weights
        model_current = EnergyModel(weights=current_weights)
        free_energy, _, _, penalties = model_current.free_energy(metrics)
        
        print(f"{scenario_name}:")
        print(f"  Latency: {latency:.0f}ms")
        print(f"  Current energy: {free_energy:.6f}")
        print(f"  Delta from target: {free_energy - tuner._target_energy:+.6f}")
        
        # Tune weights
        adjusted_weights = tuner.tune(metrics, free_energy, penalties)
        
        # Evaluate with adjusted weights
        model_adjusted = EnergyModel(weights=adjusted_weights)
        adjusted_energy, _, _, _ = model_adjusted.free_energy(metrics)
        
        print(f"  Adjusted energy: {adjusted_energy:.6f}")
        print(f"  Improvement: {free_energy - adjusted_energy:+.6f}")
        
        # Show key weight changes
        print("  Weight adjustments:")
        for metric in ["latency_p95", "latency_p99", "cpu_burn"]:
            old = current_weights[metric]
            new = adjusted_weights[metric]
            change = ((new - old) / old) * 100 if old > 0 else 0
            print(f"    {metric:20s}: {old:.3f} → {new:.3f} ({change:+.1f}%)")
        
        print()
        
        # Use adjusted weights for next iteration
        current_weights = adjusted_weights


def demo_phase_transition_detection():
    """Demonstrate phase transition detection."""
    print("=" * 70)
    print("PHASE TRANSITION DETECTION")
    print("=" * 70)
    print()
    
    detector = PhaseTransitionDetector(
        window_size=8,
        sensitivity=2.0
    )
    
    # Create sequence with phase transitions
    # Phase 1: Stable low energy (samples 0-14)
    # Transition at sample 15
    # Phase 2: Stable high energy (samples 15-29)
    # Transition at sample 30
    # Phase 3: Return to low energy (samples 30-44)
    
    model = EnergyModel()
    energy_sequence = []
    
    phases = [
        ("Stable Operation", 65.0, 15),
        ("System Stress", 120.0, 15),
        ("Recovery", 70.0, 15),
    ]
    
    print("Simulating energy evolution with phase transitions:")
    print()
    
    for phase_name, base_latency, duration in phases:
        print(f"{phase_name} (latency ~{base_latency:.0f}ms):")
        for i in range(duration):
            # Add small random variation
            import random
            latency = base_latency + random.uniform(-5, 5)
            
            metrics = EnergyMetrics(
                latency_p95=latency,
                latency_p99=latency * 1.4,
                coherency_drift=0.04,
                cpu_burn=0.5 + (latency - 60) / 200.0,
                mem_cost=5.0,
                queue_depth=25.0,
                packet_loss=0.003,
            )
            
            free_energy, _, _, _ = model.free_energy(metrics)
            energy_sequence.append(free_energy)
            
            if i < 3 or i >= duration - 2:  # Show first 3 and last 2
                print(f"  Sample {len(energy_sequence)-1:2d}: {free_energy:.6f}")
            elif i == 3:
                print("  ...")
        print()
    
    # Detect transitions
    has_transition, indices = detector.detect(energy_sequence)
    
    print(f"Phase Transition Detection:")
    print(f"  Window size: {detector._window_size}")
    print(f"  Sensitivity: {detector._sensitivity:.1f}")
    print(f"  Transitions detected: {has_transition}")
    
    if has_transition:
        print(f"  Number of transitions: {len(indices)}")
        print(f"  Transition points: {indices}")
        for idx in indices:
            print(f"    Sample {idx}: energy = {energy_sequence[idx]:.6f}")
    else:
        print("  No significant transitions detected")
    
    print()


def main():
    """Run all demonstrations."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " ENERGY MODEL OPTIMIZATION DEMONSTRATION ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    demo_gradient_descent()
    demo_simulated_annealing()
    demo_adaptive_weight_tuning()
    demo_phase_transition_detection()
    
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The energy optimization module provides sophisticated algorithms for")
    print("automatic parameter tuning and system adaptation.")
    print()


if __name__ == "__main__":
    main()
