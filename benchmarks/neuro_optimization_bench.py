#!/usr/bin/env python
"""Benchmark for neuro-optimization system performance.

This benchmark measures the performance characteristics of the adaptive
calibrator and cross-neuromodulator optimizer under various conditions.

Metrics measured:
- Calibration speed (iterations/second)
- Optimization speed (iterations/second)
- Convergence time
- Memory usage
- Score improvement over time
"""

import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import importlib.util  # noqa: E402

import numpy as np  # noqa: E402
from utils.seed import set_global_seed  # noqa: E402
from benchmarks._neuro_optimizer_loader import (  # noqa: E402
    compute_stability_score,
    load_validation,
)


def load_module(name, path):
    """Load a module from path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = 'tradepulse.core.neuro'
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load modules
neuro_path = src_path / "tradepulse" / "core" / "neuro"
adaptive_calibrator = load_module(
    "adaptive_calibrator", neuro_path / "adaptive_calibrator.py"
)
neuro_optimizer = load_module(
    "neuro_optimizer", neuro_path / "neuro_optimizer.py"
)

AdaptiveCalibrator = adaptive_calibrator.AdaptiveCalibrator
CalibrationMetrics = adaptive_calibrator.CalibrationMetrics
NeuroOptimizer = neuro_optimizer.NeuroOptimizer
OptimizationConfig = neuro_optimizer.OptimizationConfig


def benchmark_calibrator_speed(n_iterations=100):
    """Benchmark calibrator iteration speed."""
    print(f"\n{'='*60}")
    print(f"Benchmark: Calibrator Speed ({n_iterations} iterations)")
    print(f"{'='*60}")

    initial_params = {
        'dopamine': {
            'discount_gamma': 0.99,
            'learning_rate': 0.01,
            'burst_factor': 1.5,
            'base_temperature': 1.0,
        },
        'serotonin': {
            'stress_threshold': 0.15,
            'release_threshold': 0.10,
        },
        'gaba': {
            'k_inhibit': 0.4,
            'impulse_threshold': 0.5,
        },
        'na_ach': {
            'arousal_gain': 1.2,
            'attention_gain': 1.0,
        },
    }

    calibrator = AdaptiveCalibrator(initial_params)

    # Warmup
    for _ in range(5):
        metrics = CalibrationMetrics(
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.65,
            avg_hold_time=25.0,
            dopamine_stability=0.3,
            serotonin_stress=0.25,
            gaba_inhibition_rate=0.35,
            na_ach_arousal=1.1,
            total_trades=100,
            timestamp=time.time(),
        )
        calibrator.step(metrics)

    # Reset for benchmark
    calibrator = AdaptiveCalibrator(initial_params)

    # Benchmark
    start_time = time.time()
    for _ in range(n_iterations):
        metrics = CalibrationMetrics(
            sharpe_ratio=1.5 + np.random.randn() * 0.3,
            max_drawdown=0.08 + abs(np.random.randn() * 0.02),
            win_rate=0.65 + np.random.randn() * 0.05,
            avg_hold_time=25.0,
            dopamine_stability=0.3,
            serotonin_stress=0.25,
            gaba_inhibition_rate=0.35,
            na_ach_arousal=1.1,
            total_trades=100,
            timestamp=time.time(),
        )
        calibrator.step(metrics)

    end_time = time.time()
    elapsed = end_time - start_time

    print(f"Total time: {elapsed:.2f}s")
    print(f"Iterations/second: {n_iterations / elapsed:.1f}")
    print(f"Time per iteration: {elapsed / n_iterations * 1000:.2f}ms")
    print(f"Final best score: {calibrator.state.best_score:.3f}")

    return {
        'elapsed': elapsed,
        'iterations_per_second': n_iterations / elapsed,
        'ms_per_iteration': elapsed / n_iterations * 1000,
        'best_score': calibrator.state.best_score,
    }


def benchmark_optimizer_speed(n_iterations=100):
    """Benchmark optimizer iteration speed."""
    print(f"\n{'='*60}")
    print(f"Benchmark: Optimizer Speed ({n_iterations} iterations)")
    print(f"{'='*60}")

    config = OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
    )

    optimizer = NeuroOptimizer(config)
    validate_neuro_invariants = load_validation()

    params = {
        'dopamine': {'learning_rate': 0.01, 'burst_factor': 1.5},
        'serotonin': {'stress_threshold': 0.15},
        'gaba': {'k_inhibit': 0.4},
        'na_ach': {'arousal_gain': 1.2},
    }

    state = {
        'dopamine_level': 0.6,
        'serotonin_level': 0.3,
        'gaba_inhibition': 0.4,
        'na_arousal': 1.1,
        'ach_attention': 0.7,
    }

    # Warmup
    for _ in range(5):
        _, balance = optimizer.optimize(params, state, 1.5)
        stability = compute_stability_score(optimizer._performance_history)
        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability,
            da_5ht_ratio_range=optimizer.config.da_5ht_ratio_range,
            ei_balance_range=optimizer.config.ei_balance_range,
        )

    # Reset
    optimizer = NeuroOptimizer(config)

    # Benchmark
    start_time = time.time()
    for _ in range(n_iterations):
        state_varied = {
            'dopamine_level': 0.6 + np.random.randn() * 0.1,
            'serotonin_level': 0.3 + abs(np.random.randn() * 0.05),
            'gaba_inhibition': 0.4 + abs(np.random.randn() * 0.05),
            'na_arousal': 1.1 + np.random.randn() * 0.2,
            'ach_attention': 0.7 + np.random.randn() * 0.1,
        }
        _, balance = optimizer.optimize(
            params, state_varied, 1.5 + np.random.randn() * 0.3
        )
        stability = compute_stability_score(optimizer._performance_history)
        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability,
            da_5ht_ratio_range=optimizer.config.da_5ht_ratio_range,
            ei_balance_range=optimizer.config.ei_balance_range,
        )

    end_time = time.time()
    elapsed = end_time - start_time

    print(f"Total time: {elapsed:.2f}s")
    print(f"Iterations/second: {n_iterations / elapsed:.1f}")
    print(f"Time per iteration: {elapsed / n_iterations * 1000:.2f}ms")

    report = optimizer.get_optimization_report()
    print(f"Final balance score: {report['avg_balance_score']:.3f}")

    return {
        'elapsed': elapsed,
        'iterations_per_second': n_iterations / elapsed,
        'ms_per_iteration': elapsed / n_iterations * 1000,
        'balance_score': report['avg_balance_score'],
    }


def benchmark_convergence_time():
    """Benchmark time to convergence."""
    print(f"\n{'='*60}")
    print("Benchmark: Convergence Time")
    print(f"{'='*60}")

    initial_params = {
        'dopamine': {'discount_gamma': 0.99, 'learning_rate': 0.01},
        'serotonin': {'stress_threshold': 0.15},
        'gaba': {'k_inhibit': 0.4},
        'na_ach': {'arousal_gain': 1.2},
    }

    config = OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
        convergence_threshold=0.01,
    )

    optimizer = NeuroOptimizer(config)
    validate_neuro_invariants = load_validation()

    start_time = time.time()
    iteration = 0
    max_iterations = 500

    state = {
        'dopamine_level': 0.6,
        'serotonin_level': 0.3,
        'gaba_inhibition': 0.4,
        'na_arousal': 1.1,
        'ach_attention': 0.7,
    }

    while iteration < max_iterations:
        # Simulate stable performance (should converge)
        performance = 1.5 + np.random.randn() * 0.05  # Low noise

        _, balance = optimizer.optimize(initial_params, state, performance)
        stability = compute_stability_score(optimizer._performance_history)
        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability,
            da_5ht_ratio_range=optimizer.config.da_5ht_ratio_range,
            ei_balance_range=optimizer.config.ei_balance_range,
        )
        iteration += 1

        # Check convergence every 20 iterations
        if iteration >= 20 and iteration % 20 == 0:
            report = optimizer.get_optimization_report()
            if report['convergence']['converged']:
                end_time = time.time()
                elapsed = end_time - start_time

                print(f"Converged at iteration: {iteration}")
                print(f"Time to convergence: {elapsed:.2f}s")
                print(f"Convergence variance: {report['convergence']['variance']:.4f}")

                return {
                    'iterations_to_converge': iteration,
                    'time_to_converge': elapsed,
                    'convergence_variance': report['convergence']['variance'],
                }

    print("Did not converge within max iterations")
    return {
        'iterations_to_converge': max_iterations,
        'time_to_converge': time.time() - start_time,
        'converged': False,
    }


def benchmark_score_improvement():
    """Benchmark score improvement over iterations."""
    print(f"\n{'='*60}")
    print("Benchmark: Score Improvement Over Time")
    print(f"{'='*60}")

    initial_params = {
        'dopamine': {'discount_gamma': 0.95, 'learning_rate': 0.005},
        'serotonin': {'stress_threshold': 0.20},
        'gaba': {'k_inhibit': 0.3},
        'na_ach': {'arousal_gain': 1.0},
    }

    calibrator = AdaptiveCalibrator(
        initial_params,
        temperature_initial=1.0,
        temperature_decay=0.98,
    )

    # Simulate improving performance
    scores = []
    for i in range(50):
        # Gradually improve base performance
        base_sharpe = 0.5 + i * 0.03

        metrics = CalibrationMetrics(
            sharpe_ratio=base_sharpe + np.random.randn() * 0.2,
            max_drawdown=0.15 - i * 0.002,
            win_rate=0.45 + i * 0.005,
            avg_hold_time=30.0,
            dopamine_stability=0.3,
            serotonin_stress=0.3,
            gaba_inhibition_rate=0.4,
            na_ach_arousal=1.0,
            total_trades=50 + i * 2,
            timestamp=time.time(),
        )

        calibrator.step(metrics)
        scores.append(calibrator.state.best_score)

    initial_score = scores[0]
    final_score = scores[-1]
    improvement = (final_score - initial_score) / initial_score * 100

    print(f"Initial best score: {initial_score:.3f}")
    print(f"Final best score: {final_score:.3f}")
    print(f"Improvement: {improvement:.1f}%")
    print(f"Average improvement per iteration: {improvement/50:.2f}%")

    return {
        'initial_score': initial_score,
        'final_score': final_score,
        'improvement_percent': improvement,
        'avg_improvement_per_iter': improvement / 50,
    }


def benchmark_memory_usage():
    """Benchmark memory usage over long runs."""
    print(f"\n{'='*60}")
    print("Benchmark: Memory Usage")
    print(f"{'='*60}")

    import tracemalloc

    initial_params = {
        'dopamine': {'discount_gamma': 0.99, 'learning_rate': 0.01},
        'serotonin': {'stress_threshold': 0.15},
        'gaba': {'k_inhibit': 0.4},
        'na_ach': {'arousal_gain': 1.2},
    }

    tracemalloc.start()

    # Measure calibrator memory
    calibrator = AdaptiveCalibrator(initial_params)

    for _ in range(1000):
        metrics = CalibrationMetrics(
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.65,
            avg_hold_time=25.0,
            dopamine_stability=0.3,
            serotonin_stress=0.25,
            gaba_inhibition_rate=0.35,
            na_ach_arousal=1.1,
            total_trades=100,
            timestamp=time.time(),
        )
        calibrator.step(metrics)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Current memory: {current / 1024 / 1024:.2f} MB")
    print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
    print(f"History entries: {len(calibrator.state.metrics_history)}")

    return {
        'current_mb': current / 1024 / 1024,
        'peak_mb': peak / 1024 / 1024,
        'history_size': len(calibrator.state.metrics_history),
    }


def main():
    """Run all benchmarks."""
    print("\n" + "="*60)
    print("Neuro-Optimization System Benchmark Suite")
    print("="*60)

    results = {}

    # Run benchmarks
    results['calibrator_speed'] = benchmark_calibrator_speed(100)
    results['optimizer_speed'] = benchmark_optimizer_speed(100)
    results['convergence'] = benchmark_convergence_time()
    results['score_improvement'] = benchmark_score_improvement()
    results['memory'] = benchmark_memory_usage()

    # Summary
    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}")

    print("\nPerformance:")
    print(f"  Calibrator: {results['calibrator_speed']['iterations_per_second']:.1f} iter/s")
    print(f"  Optimizer: {results['optimizer_speed']['iterations_per_second']:.1f} iter/s")

    print("\nConvergence:")
    if results['convergence'].get('converged', True):
        print(f"  Iterations: {results['convergence']['iterations_to_converge']}")
        print(f"  Time: {results['convergence']['time_to_converge']:.2f}s")
    else:
        print("  Did not converge")

    print("\nScore Improvement:")
    print(f"  Initial: {results['score_improvement']['initial_score']:.3f}")
    print(f"  Final: {results['score_improvement']['final_score']:.3f}")
    print(f"  Improvement: {results['score_improvement']['improvement_percent']:.1f}%")

    print("\nMemory Usage:")
    print(f"  Peak: {results['memory']['peak_mb']:.2f} MB")
    print(f"  Current: {results['memory']['current_mb']:.2f} MB")

    print("\n" + "="*60)
    print("✓ All benchmarks completed successfully")
    print("="*60 + "\n")

    return results


if __name__ == "__main__":
    set_global_seed()  # For reproducibility
    main()
