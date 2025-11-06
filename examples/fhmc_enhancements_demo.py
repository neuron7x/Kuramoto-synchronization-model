"""Example demonstrating FHMC enhancements from 2025 audit.

This script showcases:
1. Online biomarker monitoring with sliding window DFA-α
2. A/B testing protocols with regime-shift validation
3. Continual learning metrics (FID, retention, backward transfer)
4. Self-rewarding RL for dynamic learning rate tuning
5. White noise detection fallback
6. Hölder exponent computation for fractional diffusion
"""
from __future__ import annotations

import numpy as np
from pathlib import Path

# Import FHMC and validation components
from runtime.thermo_controller import FHMC
from core.validation.ab_testing import ABTestProtocol, RegimeShiftSimulator
from core.validation.continual_learning_metrics import (
    ContinualLearningEvaluator,
    SelfRewardingRL,
)
from core.metrics.online_biomarkers import OnlineBiomarkerMonitor


def demonstrate_online_biomarker_monitoring():
    """Demonstrate real-time biomarker monitoring with sliding window."""
    print("\n=== 1. Online Biomarker Monitoring ===")
    
    monitor = OnlineBiomarkerMonitor(
        window_size=2000,
        alpha_target=(0.8, 1.0),
    )
    
    # Simulate trading actions over time
    np.random.seed(42)
    actions = np.cumsum(np.random.randn(1000) * 0.1)
    
    for action in actions:
        monitor.update(action)
    
    # Compute DFA-α
    alpha = monitor.compute_alpha()
    if alpha is not None:
        print(f"  DFA-α: {alpha:.4f}")
        print(f"  In target range [0.8, 1.0]: {monitor.is_in_target_range(alpha)}")
        print(f"  White noise detected: {monitor.detect_white_noise(alpha)}")
    
    # Get comprehensive biomarker state
    state = monitor.get_state()
    print(f"  Retention metric: {state.retention_metric:.4f}")
    print(f"  Backward transfer: {state.backward_transfer:.4f}")
    print(f"  Convergence rate: {state.convergence_rate:.4f}")
    
    # Compute Hölder exponent for fractional diffusion
    holder = monitor.compute_holder_exponent(actions)
    print(f"  Hölder exponent: {holder:.4f}")


def demonstrate_ab_testing():
    """Demonstrate A/B testing with regime-shift validation."""
    print("\n=== 2. A/B Testing Protocol ===")
    
    protocol = ABTestProtocol(
        sharpe_improvement_threshold=0.05,  # 5% improvement target
        drawdown_improvement_threshold=0.15,  # 15% reduction target
    )
    
    # Simulate baseline trading returns
    np.random.seed(42)
    baseline_returns = np.random.randn(252) * 0.02 + 0.0005
    baseline_alphas = np.random.uniform(0.5, 0.7, 20)
    
    # Simulate treatment (with FHMC enhancements) returns
    treatment_returns = np.random.randn(252) * 0.018 + 0.001  # Lower vol, higher mean
    treatment_alphas = np.random.uniform(0.8, 1.0, 20)  # Better alpha stability
    
    # Run A/B test
    result = protocol.run_test(
        baseline_returns,
        treatment_returns,
        baseline_alphas,
        treatment_alphas,
    )
    
    print(f"  Baseline Sharpe: {result.baseline_metrics.sharpe_ratio:.4f}")
    print(f"  Treatment Sharpe: {result.treatment_metrics.sharpe_ratio:.4f}")
    print(f"  Sharpe improvement: {result.sharpe_improvement * 100:.2f}%")
    print(f"  MaxDD improvement: {result.drawdown_improvement * 100:.2f}%")
    print(f"  Alpha stability improvement: {result.alpha_improvement:.4f}")
    print(f"  Statistical significance: {result.statistical_significance:.4f}")
    print(f"  Test passed: {result.test_passed}")
    print(f"  Regime shift detected: {result.regime_shift_detected}")


def demonstrate_regime_shift_simulation():
    """Demonstrate regime shift generation and detection."""
    print("\n=== 3. Regime Shift Simulation ===")
    
    sim = RegimeShiftSimulator(base_volatility=0.02, shock_multiplier=2.0)
    
    # Generate volatility shock
    vol_series = sim.generate_shock(duration=1000, shock_magnitude=2.5)
    print(f"  Volatility shock generated (duration=1000, multiplier=2.5)")
    print(f"  Base volatility: {np.min(vol_series):.4f}")
    print(f"  Peak volatility: {np.max(vol_series):.4f}")
    
    # Generate returns with regime shift
    np.random.seed(42)
    returns = np.random.randn(1000) * vol_series
    
    # Detect regime shift
    detected = sim.detect_regime_shift(returns, threshold=1.5)
    print(f"  Regime shift detected (threshold=1.5): {detected}")


def demonstrate_continual_learning_metrics():
    """Demonstrate continual learning evaluation."""
    print("\n=== 4. Continual Learning Metrics ===")
    
    evaluator = ContinualLearningEvaluator(task_dimension=10)
    
    # Simulate learning on multiple tasks
    tasks = ["energy_futures", "fx_pairs", "crypto_spot"]
    
    for task in tasks:
        # Initial performance
        initial_perf = np.random.uniform(0.6, 0.8)
        evaluator.record_task_performance(task, initial_perf)
        
        # After learning
        for _ in range(3):
            perf = initial_perf + np.random.uniform(0.0, 0.1)
            evaluator.record_task_performance(task, perf)
    
    # Generate embeddings for FID score
    np.random.seed(42)
    real_embeddings = np.random.randn(50, 10)
    generated_embeddings = real_embeddings + np.random.randn(50, 10) * 0.2
    
    # Evaluate metrics
    metrics = evaluator.evaluate(real_embeddings.flatten(), generated_embeddings.flatten())
    
    print(f"  FID score: {metrics.fid_score:.4f} (target: <50)")
    print(f"  Retention rate: {metrics.retention_rate:.4f} (target: ≥0.9)")
    print(f"  Backward transfer: {metrics.backward_transfer:.4f} (positive is good)")
    print(f"  Forward transfer: {metrics.forward_transfer:.4f}")
    print(f"  Catastrophic forgetting index: {metrics.catastrophic_forgetting_index:.4f} (target: <0.2)")


def demonstrate_self_rewarding_rl():
    """Demonstrate self-rewarding RL for dynamic learning rate tuning."""
    print("\n=== 5. Self-Rewarding RL ===")
    
    srdrl = SelfRewardingRL(
        initial_lr=3e-4,
        lr_min=1e-5,
        lr_max=1e-3,
    )
    
    print(f"  Initial learning rate: {srdrl.current_lr:.6f}")
    
    # Simulate training with improving rewards
    rewards = [0.5, 0.55, 0.6, 0.58, 0.65, 0.7]
    convergence_rates = [-0.1, -0.08, -0.05, -0.03, -0.02, -0.01]
    
    for i, (reward, conv_rate) in enumerate(zip(rewards, convergence_rates)):
        new_lr = srdrl.update_lr(reward, conv_rate)
        print(f"  Step {i+1}: reward={reward:.2f}, conv_rate={conv_rate:.3f} → lr={new_lr:.6f}")
    
    schedule = srdrl.get_lr_schedule()
    print(f"  Learning rate schedule length: {len(schedule)}")


def demonstrate_fhmc_integration():
    """Demonstrate FHMC with all enhancements integrated."""
    print("\n=== 6. FHMC Integration ===")
    
    # Load FHMC configuration
    config_path = Path("configs/fhmc.yaml")
    if not config_path.exists():
        print(f"  Config file not found: {config_path}")
        print("  Skipping FHMC integration demo")
        return
    
    try:
        fhmc = FHMC.from_yaml(config_path)
        print(f"  FHMC loaded from {config_path}")
        
        # Check online monitoring
        print(f"  Online monitoring enabled: {fhmc._online_monitor is not None}")
        
        # Simulate biomarker updates
        actions = np.cumsum(np.random.randn(1000) * 0.1)
        latents = np.random.randn(1000)
        
        fhmc.update_biomarkers(actions, latents)
        
        # Get biomarker state
        biomarker_state = fhmc.get_online_biomarker_state()
        if biomarker_state:
            print(f"  Current α: {biomarker_state['alpha']:.4f}")
            print(f"  Hölder exponent: {biomarker_state['holder_exponent']:.4f}")
            print(f"  Retention: {biomarker_state['retention_metric']:.4f}")
        
        # Compute threat and orexin
        fhmc.compute_threat(maxdd=0.15, volshock=1.2, cp_score=2.5)
        fhmc.compute_orexin(exp_return=0.001, novelty=0.3, load=0.5)
        
        # Flip-flop state
        state = fhmc.flipflop_step()
        print(f"  Current state: {state}")
        print(f"  Orexin: {fhmc.orexin_value():.4f}")
        print(f"  Threat: {fhmc.threat_value():.4f}")
        
    except Exception as e:
        print(f"  Error loading FHMC: {e}")


def main():
    """Run all demonstrations."""
    print("\n" + "="*60)
    print("FHMC 2025 Audit Enhancements Demonstration")
    print("="*60)
    
    demonstrate_online_biomarker_monitoring()
    demonstrate_ab_testing()
    demonstrate_regime_shift_simulation()
    demonstrate_continual_learning_metrics()
    demonstrate_self_rewarding_rl()
    demonstrate_fhmc_integration()
    
    print("\n" + "="*60)
    print("All demonstrations completed successfully!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
