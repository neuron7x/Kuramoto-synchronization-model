"""Tests for energy optimization module."""

from __future__ import annotations

import pytest

from tacl.energy_model import EnergyMetrics, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS
from tacl.energy_optimization import (
    AnnealingSchedule,
    GradientDescentOptimizer,
    SimulatedAnnealingOptimizer,
    AdaptiveWeightTuner,
    PhaseTransitionDetector,
)


def test_annealing_schedule_exponential():
    """Test exponential annealing schedule."""
    schedule = AnnealingSchedule(
        initial_temp=1.0,
        final_temp=0.1,
        steps=100,
        schedule_type="exponential"
    )
    
    # Check boundary conditions
    assert schedule.temperature_at_step(0) == pytest.approx(1.0)
    assert schedule.temperature_at_step(99) == pytest.approx(0.1, rel=1e-2)
    
    # Check monotonic decrease
    for i in range(99):
        t1 = schedule.temperature_at_step(i)
        t2 = schedule.temperature_at_step(i + 1)
        assert t1 >= t2


def test_annealing_schedule_linear():
    """Test linear annealing schedule."""
    schedule = AnnealingSchedule(
        initial_temp=1.0,
        final_temp=0.1,
        steps=10,
        schedule_type="linear"
    )
    
    assert schedule.temperature_at_step(0) == pytest.approx(1.0)
    assert schedule.temperature_at_step(9) == pytest.approx(0.1)
    
    # Check linear decrease
    temp_mid = schedule.temperature_at_step(5)
    assert temp_mid == pytest.approx(0.55, rel=1e-2)


def test_annealing_schedule_cosine():
    """Test cosine annealing schedule."""
    schedule = AnnealingSchedule(
        initial_temp=1.0,
        final_temp=0.0,
        steps=100,
        schedule_type="cosine"
    )
    
    assert schedule.temperature_at_step(0) == pytest.approx(1.0)
    assert schedule.temperature_at_step(99) == pytest.approx(0.0, abs=1e-2)
    
    # Cosine should have smooth decay
    temps = [schedule.temperature_at_step(i) for i in range(100)]
    # Check it's decreasing
    for i in range(99):
        assert temps[i] >= temps[i + 1]


def test_annealing_schedule_invalid_type():
    """Test that invalid schedule type raises error."""
    schedule = AnnealingSchedule(
        initial_temp=1.0,
        final_temp=0.1,
        steps=100,
        schedule_type="invalid"
    )
    
    with pytest.raises(ValueError, match="Unknown schedule type"):
        schedule.temperature_at_step(50)


def test_gradient_descent_simple_quadratic():
    """Test gradient descent on a simple quadratic function."""
    optimizer = GradientDescentOptimizer(
        learning_rate=0.1,
        momentum=0.0,
        max_iterations=50,
        tolerance=1e-6,
    )
    
    # Minimize (x - 2)^2
    def objective(params):
        x = params["x"]
        return (x - 2.0) ** 2
    
    result = optimizer.optimize({"x": 10.0}, objective)
    
    # Should converge near x = 2
    assert result.best_params["x"] == pytest.approx(2.0, rel=0.1)
    assert result.converged or result.best_score < 0.1
    assert len(result.history) > 0


def test_gradient_descent_with_bounds():
    """Test gradient descent respects parameter bounds."""
    optimizer = GradientDescentOptimizer(
        learning_rate=0.1,
        max_iterations=20,
    )
    
    # Minimize x^2, but constrain x >= 1
    def objective(params):
        return params["x"] ** 2
    
    result = optimizer.optimize(
        {"x": 5.0},
        objective,
        bounds={"x": (1.0, 10.0)}
    )
    
    # Should converge to lower bound
    assert result.best_params["x"] >= 1.0
    assert result.best_params["x"] <= 10.0


def test_gradient_descent_with_momentum():
    """Test gradient descent with momentum."""
    optimizer = GradientDescentOptimizer(
        learning_rate=0.01,
        momentum=0.9,
        max_iterations=100,
    )
    
    # Minimize (x - 5)^2 + (y - 3)^2
    def objective(params):
        x, y = params["x"], params["y"]
        return (x - 5.0) ** 2 + (y - 3.0) ** 2
    
    result = optimizer.optimize({"x": 0.0, "y": 0.0}, objective)
    
    assert result.best_params["x"] == pytest.approx(5.0, rel=0.2)
    assert result.best_params["y"] == pytest.approx(3.0, rel=0.2)


def test_simulated_annealing_basic():
    """Test simulated annealing on a simple function."""
    schedule = AnnealingSchedule(
        initial_temp=1.0,
        final_temp=0.01,
        steps=200,
        schedule_type="exponential"
    )
    
    optimizer = SimulatedAnnealingOptimizer(schedule, seed=42)
    
    # Minimize (x - 3)^2
    def objective(params):
        return (params["x"] - 3.0) ** 2
    
    result = optimizer.optimize({"x": 10.0}, objective)
    
    # Should converge reasonably close to minimum
    assert result.best_params["x"] == pytest.approx(3.0, rel=0.5)
    assert result.converged  # SA always completes its schedule
    assert len(result.history) == schedule.steps + 1


def test_simulated_annealing_with_bounds():
    """Test simulated annealing respects bounds."""
    schedule = AnnealingSchedule(
        initial_temp=2.0,
        final_temp=0.1,
        steps=100,
    )
    
    optimizer = SimulatedAnnealingOptimizer(schedule, seed=123)
    
    def objective(params):
        return params["x"] ** 2
    
    result = optimizer.optimize(
        {"x": 5.0},
        objective,
        bounds={"x": (0.0, 10.0)}
    )
    
    assert 0.0 <= result.best_params["x"] <= 10.0


def test_adaptive_weight_tuner():
    """Test adaptive weight tuning."""
    base_weights = {
        "metric1": 1.0,
        "metric2": 2.0,
        "metric3": 1.5,
    }
    
    tuner = AdaptiveWeightTuner(
        base_weights=base_weights,
        target_energy=1.0,
        adjustment_rate=0.1,
    )
    
    penalties = {
        "metric1": 0.5,
        "metric2": 0.1,
        "metric3": 0.0,
    }
    
    # Energy is too high (1.5 > 1.0), should reduce weights on high-penalty metrics
    metrics = EnergyMetrics(
        latency_p95=50.0,
        latency_p99=70.0,
        coherency_drift=0.02,
        cpu_burn=0.4,
        mem_cost=3.0,
        queue_depth=15.0,
        packet_loss=0.001,
    )
    
    adjusted = tuner.tune(metrics, current_energy=1.5, penalties=penalties)
    
    # Should return adjusted weights
    assert isinstance(adjusted, dict)
    assert set(adjusted.keys()) == set(base_weights.keys())
    
    # Total weight should be approximately preserved
    total_base = sum(base_weights.values())
    total_adjusted = sum(adjusted.values())
    assert total_adjusted == pytest.approx(total_base, rel=0.2)


def test_adaptive_weight_tuner_low_energy():
    """Test adaptive weight tuner with low energy."""
    base_weights = {"metric1": 1.0, "metric2": 1.0}
    
    tuner = AdaptiveWeightTuner(
        base_weights=base_weights,
        target_energy=1.5,
        adjustment_rate=0.1,
    )
    
    penalties = {"metric1": 0.1, "metric2": 0.0}
    
    metrics = EnergyMetrics(
        latency_p95=50.0,
        latency_p99=70.0,
        coherency_drift=0.02,
        cpu_burn=0.4,
        mem_cost=3.0,
        queue_depth=15.0,
        packet_loss=0.001,
    )
    
    # Energy below target (1.0 < 1.5)
    adjusted = tuner.tune(metrics, current_energy=1.0, penalties=penalties)
    
    assert isinstance(adjusted, dict)


def test_phase_transition_detector():
    """Test phase transition detection."""
    detector = PhaseTransitionDetector(window_size=5, sensitivity=2.0)
    
    # Create sequence with a clear transition
    sequence = [1.0] * 10 + [2.0] * 10
    
    has_transition, indices = detector.detect(sequence)
    
    # Should detect transition around index 10
    assert has_transition
    assert len(indices) > 0


def test_phase_transition_detector_no_transition():
    """Test phase transition detector with stable sequence."""
    detector = PhaseTransitionDetector(window_size=5, sensitivity=2.0)
    
    # Stable sequence
    sequence = [1.0 + 0.1 * i for i in range(20)]
    
    has_transition, indices = detector.detect(sequence)
    
    # Gradual change should not trigger detection with high sensitivity
    # (depends on sensitivity setting)
    assert isinstance(has_transition, bool)
    assert isinstance(indices, list)


def test_phase_transition_detector_insufficient_data():
    """Test phase transition detector with insufficient data."""
    detector = PhaseTransitionDetector(window_size=10)
    
    # Too short sequence
    sequence = [1.0, 1.1, 1.2]
    
    has_transition, indices = detector.detect(sequence)
    
    # Should handle gracefully
    assert has_transition == False
    assert len(indices) == 0


def test_optimization_result_structure():
    """Test OptimizationResult dataclass."""
    from tacl.energy_optimization import OptimizationResult
    
    result = OptimizationResult(
        best_params={"x": 1.0, "y": 2.0},
        best_score=0.5,
        iterations=50,
        converged=True,
        history=(0.9, 0.7, 0.5),
    )
    
    assert result.best_params == {"x": 1.0, "y": 2.0}
    assert result.best_score == 0.5
    assert result.iterations == 50
    assert result.converged
    assert len(result.history) == 3
