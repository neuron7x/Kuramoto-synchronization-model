# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
HPC-AI v4 Demonstration: Complete Integration Example

This example demonstrates the full pipeline of the Hierarchical Predictive Coding
with Active Inference (HPC-AI v4) module for adaptive trading.
"""

from core.utils.determinism import DEFAULT_SEED
from geosync_hpc.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from geosync_hpc.hpc_validation import (
    calibrate_perturbation_scale,
    format_validation_report,
    generate_synthetic_data,
    simple_backtest,
    validate_hpc_ai,
)


def main():
    print("=" * 80)
    print("HPC-AI v4 - Hierarchical Predictive Coding with Active Inference")
    print("Demonstration: Complete Integration for Adaptive Trading")
    print("=" * 80)
    print()

    # Step 1: Generate synthetic market data
    print("Step 1: Generating Synthetic Market Data")
    print("-" * 80)
    data = generate_synthetic_data(
        n_days=1000, initial_price=100.0, volatility=0.5, seed=DEFAULT_SEED
    )
    print(f"Generated {len(data)} days of synthetic OHLCV data")
    print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print(f"Mean volume: {data['volume'].mean():.0f}")
    print()

    # Step 2: Initialize HPC-AI model
    print("Step 2: Initializing HPC-AI Module")
    print("-" * 80)
    model = HPCActiveInferenceModuleV4(
        input_dim=10,
        state_dim=128,
        action_dim=3,
        hidden_dim=256,
        hpc_levels=3,
        learning_rate=1e-4,
    )
    print("Model initialized with:")
    print("  - Input dimension: 10 (OHLCV + 5 indicators)")
    print("  - State dimension: 128")
    print("  - Action dimension: 3 (Hold, Buy, Sell)")
    print("  - HPC levels: 3")
    print(f"  - Device: {model.device}")
    print()

    # Step 3: Calibrate perturbation scale
    print("Step 3: Calibrating Perturbation Scale")
    print("-" * 80)
    best_epsilon, calibration_results = calibrate_perturbation_scale(
        model,
        data,
        epsilon_grid=[0.005, 0.01, 0.02],
        n_steps=10,
    )
    print("Calibration results:")
    for eps, sharpe in calibration_results.items():
        marker = " <-- BEST" if eps == best_epsilon else ""
        print(f"  ε={eps:.3f}: Sharpe proxy={sharpe:.2f}{marker}")
    print(f"\nOptimal perturbation scale: {best_epsilon:.3f}")
    print()

    # Step 4: Validate model on synthetic data
    print("Step 4: Validating HPC-AI on Synthetic Data")
    print("-" * 80)
    metrics = validate_hpc_ai(model, data, n_steps=20)
    print("Validation Metrics:")
    print(f"  Mean PWPE: {metrics.mean_pwpe:.4f}")
    print(f"  Std PWPE: {metrics.std_pwpe:.4f}")
    print(f"  Action Diversity: {metrics.action_diversity:.2%}")
    print(f"  Mean TD Error: {metrics.mean_td_error:.4f}")
    print(f"  Var TD Error: {metrics.var_td_error:.6f}")
    print(f"  Sharpe Proxy: {metrics.sharpe_proxy:.2f}")
    print()
    print("Learned Parameters:")
    print(f"  Alpha (blending): {metrics.final_alpha:.4f}")
    print(f"  Sigma (perturbation): {metrics.final_sigma:.4f}")
    print(f"  Beta (gate threshold): {metrics.final_beta:.4f}")
    print()

    # Step 5: Run simple backtest
    print("Step 5: Running Simple Backtest")
    print("-" * 80)
    backtest_results = simple_backtest(
        model,
        data,
        initial_capital=10000.0,
        position_size=0.1,
    )
    print("Backtest Results:")
    print(f"  Total Return: {backtest_results['total_return']:.2%}")
    print(f"  Sharpe Ratio: {backtest_results['sharpe']:.4f}")
    print(f"  Max Drawdown: {backtest_results['max_drawdown']:.2%}")
    print(f"  Number of Trades: {backtest_results['n_trades']}")
    print(f"  Mean PWPE: {backtest_results['mean_pwpe']:.4f}")
    print(f"  Final Capital: ${backtest_results['final_capital']:.2f}")
    print()
    print("Action Distribution:")
    dist = backtest_results["action_distribution"]
    print(f"  Hold: {dist['hold']:.1%}")
    print(f"  Buy:  {dist['buy']:.1%}")
    print(f"  Sell: {dist['sell']:.1%}")
    print()

    # Step 6: Generate full validation report
    print("Step 6: Generating Full Validation Report")
    print("-" * 80)
    report = format_validation_report(metrics, backtest_results)
    print(report)

    # Step 7: Demonstrate action decision on latest data
    print("Step 7: Demonstrating Action Decision on Latest Data")
    print("-" * 80)
    latest_window = data.iloc[-100:]
    action = model.decide_action(latest_window, prev_pwpe=0.0)
    pwpe = model.get_pwpe(latest_window)
    state = model.get_state_representation(latest_window)

    action_names = {0: "HOLD", 1: "BUY", 2: "SELL"}
    print(f"Latest price: ${data.iloc[-1]['close']:.2f}")
    print(f"Decision: {action_names[action]}")
    print(f"PWPE (uncertainty): {pwpe:.4f}")
    print(f"State representation norm: {state.norm().item():.4f}")
    print()

    # Summary
    print("=" * 80)
    print("Demonstration Complete!")
    print("=" * 80)
    print("\nKey Achievements:")
    print(f"  ✓ Calibrated perturbation scale: {best_epsilon:.3f}")
    print(f"  ✓ Achieved Sharpe ratio: {backtest_results['sharpe']:.4f}")
    print(f"  ✓ Action diversity: {metrics.action_diversity:.1%}")
    print(f"  ✓ Mean PWPE: {metrics.mean_pwpe:.4f}")
    print(f"  ✓ Total return: {backtest_results['total_return']:.2%}")
    print()
    print("The HPC-AI v4 module successfully:")
    print("  - Integrates hierarchical predictive coding with active inference")
    print("  - Learns adaptive trading policies through self-rewarding RL")
    print("  - Detects metastable market phase transitions")
    print("  - Provides uncertainty-aware action selection via Gumbel-Softmax")
    print()


if __name__ == "__main__":
    main()
