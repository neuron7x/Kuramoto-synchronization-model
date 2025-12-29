#!/usr/bin/env python
"""Simple validation script for neuro-optimization modules.

This script validates the core functionality without requiring full dependencies.
"""

import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Check numpy availability
try:
    import numpy as np
    print("✓ NumPy available")
except ImportError:
    print("✗ NumPy not available - install with: pip install numpy")
    sys.exit(1)

from core.utils.determinism import DEFAULT_SEED
from utils.seed import set_global_seed

SEED = DEFAULT_SEED
set_global_seed(SEED)

# Import modules directly (bypassing package __init__.py)
import importlib.util


def load_module(name, path):
    """Load a module from path without triggering package imports."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Set __package__ to avoid AttributeError with dataclasses
    module.__package__ = 'tradepulse.core.neuro'
    # Register in sys.modules so dataclasses can find it
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# Load modules
neuro_path = src_path / "tradepulse" / "core" / "neuro"

print("\nLoading modules...")
adaptive_calibrator = load_module(
    "adaptive_calibrator",
    neuro_path / "adaptive_calibrator.py"
)
print("✓ Loaded adaptive_calibrator")

neuro_optimizer = load_module(
    "neuro_optimizer",
    neuro_path / "neuro_optimizer.py"
)
print("✓ Loaded neuro_optimizer")

# Extract classes
AdaptiveCalibrator = adaptive_calibrator.AdaptiveCalibrator
CalibrationMetrics = adaptive_calibrator.CalibrationMetrics
NeuroOptimizer = neuro_optimizer.NeuroOptimizer
OptimizationConfig = neuro_optimizer.OptimizationConfig

print("\n" + "=" * 60)
print("VALIDATION TESTS")
print("=" * 60)

# Test 1: AdaptiveCalibrator initialization
print("\n1. Testing AdaptiveCalibrator initialization...")
try:
    initial_params = {
        'dopamine': {
            'discount_gamma': 0.99,
            'learning_rate': 0.01,
            'burst_factor': 1.5,
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
    assert calibrator.state.iteration == 0
    assert calibrator.state.temperature == 1.0
    print("   ✓ Calibrator initialized successfully")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test 2: CalibrationMetrics creation
print("\n2. Testing CalibrationMetrics...")
try:
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

    score = metrics.composite_score()
    assert 0 <= score <= 1
    print(f"   ✓ Metrics created, composite score: {score:.3f}")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test 3: Calibrator step
print("\n3. Testing calibrator step...")
try:
    new_params = calibrator.step(metrics)
    assert isinstance(new_params, dict)
    assert calibrator.state.iteration == 1
    assert len(calibrator.state.metrics_history) == 1
    print("   ✓ Calibrator step executed successfully")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test 4: NeuroOptimizer initialization
print("\n4. Testing NeuroOptimizer initialization...")
try:
    config = OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
    )

    optimizer = NeuroOptimizer(config)
    assert optimizer._iteration == 0
    print("   ✓ Optimizer initialized successfully")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test 5: Optimizer step
print("\n5. Testing optimizer step...")
try:
    sample_state = {
        'dopamine_level': 0.6,
        'serotonin_level': 0.3,
        'gaba_inhibition': 0.4,
        'na_arousal': 1.1,
        'ach_attention': 0.7,
    }

    updated_params, balance = optimizer.optimize(
        initial_params,
        sample_state,
        performance_score=1.5,
    )

    assert isinstance(updated_params, dict)
    assert optimizer._iteration == 1
    print(f"   ✓ Optimizer step executed, balance score: {balance.overall_balance_score:.3f}")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test 6: Mini optimization loop
print("\n6. Testing mini optimization loop (10 iterations)...")
try:
    current_params = initial_params.copy()

    for i in range(10):
        # Simulate varying performance
        perf = 1.0 + i * 0.05 + np.random.randn() * 0.1

        # Create metrics
        metrics = CalibrationMetrics(
            sharpe_ratio=max(0, perf),
            max_drawdown=0.08 + abs(np.random.randn() * 0.02),
            win_rate=0.6 + np.random.randn() * 0.05,
            avg_hold_time=25.0,
            dopamine_stability=0.3,
            serotonin_stress=0.25,
            gaba_inhibition_rate=0.35,
            na_ach_arousal=1.1,
            total_trades=100 + i * 10,
            timestamp=time.time(),
        )

        # Calibrate
        current_params = calibrator.step(metrics)

        # Simulate neuromodulator state
        neuro_state = {
            'dopamine_level': 0.5 + np.random.randn() * 0.1,
            'serotonin_level': 0.3 + abs(np.random.randn() * 0.05),
            'gaba_inhibition': 0.4 + abs(np.random.randn() * 0.05),
            'na_arousal': 1.0 + np.random.randn() * 0.2,
            'ach_attention': 0.7 + np.random.randn() * 0.1,
        }

        # Optimize
        current_params, balance = optimizer.optimize(
            current_params,
            neuro_state,
            metrics.composite_score(),
        )

    print("   ✓ Completed 10 iterations")
    print(f"   Final best score: {calibrator.state.best_score:.3f}")
    print(f"   Final balance: {balance.overall_balance_score:.3f}")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Report generation
print("\n7. Testing report generation...")
try:
    cal_report = calibrator.get_calibration_report()
    assert cal_report['status'] == 'active'
    assert 'best_score' in cal_report
    assert 'recommendations' in cal_report

    opt_report = optimizer.get_optimization_report()
    assert opt_report['status'] == 'active'
    assert 'health_status' in opt_report

    print("   ✓ Reports generated successfully")
    print(f"   Calibration status: {cal_report['exploration_state']}")
    print(f"   Health status: {opt_report['health_status']['status']}")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL VALIDATION TESTS PASSED")
print("=" * 60)

print("\nSummary:")
print(f"  • AdaptiveCalibrator: {calibrator.state.iteration} iterations")
print(f"  • Best calibration score: {calibrator.state.best_score:.3f}")
print(f"  • NeuroOptimizer: {optimizer._iteration} iterations")
print(f"  • Current balance score: {balance.overall_balance_score:.3f}")
print(f"  • DA/5-HT ratio: {balance.dopamine_serotonin_ratio:.2f}")
print(f"  • E/I balance: {balance.gaba_excitation_balance:.2f}")

print("\nRecommendations:")
for rec in cal_report['recommendations']:
    print(f"  • {rec}")

print("\n✓ Neuro-optimization modules are functional and ready for use!")
