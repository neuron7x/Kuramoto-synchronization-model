# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Example integration of ECS Regulator with FractalMotivationController.

This demonstrates how to combine the ECS-Inspired Regulator with GeoSync's
existing FractalMotivationController for enhanced decision-making.
"""

import sys
from pathlib import Path

# Direct imports to avoid dependency issues
sys.path.insert(0, str(Path(__file__).parent.parent))

import importlib.util

import numpy as np

from core.utils.determinism import DEFAULT_SEED, seed_numpy

# Load ECS regulator
spec_ecs = importlib.util.spec_from_file_location(
    "core.neuro.ecs_regulator",
    Path(__file__).parent.parent / "core" / "neuro" / "ecs_regulator.py",
)
ecs_module = importlib.util.module_from_spec(spec_ecs)
sys.modules["core.neuro.ecs_regulator"] = ecs_module
spec_ecs.loader.exec_module(ecs_module)

ECSInspiredRegulator = ecs_module.ECSInspiredRegulator


def simulate_integrated_trading(n_steps: int = 100, seed: int = DEFAULT_SEED):
    """Simulate trading with ECS + Motivation integration."""

    print("=" * 70)
    print("ECS + FractalMotivation Integration Demo")
    print("=" * 70)
    print()

    # Initialize regulators
    print("Initializing controllers...")
    ecs_reg = ECSInspiredRegulator(
        initial_risk_threshold=0.05,
        stress_threshold=0.1,
        chronic_threshold=5,
        seed=seed,
    )

    # Note: FractalMotivationController requires torch and other dependencies
    # For this demo, we'll simulate its behavior
    print("  ✓ ECS Regulator initialized")
    print(f"    - Risk threshold: {ecs_reg.risk_threshold:.4f}")
    print(f"    - Stress threshold: {ecs_reg.stress_threshold:.4f}")
    print()

    # Simulate market data
    print(f"Simulating {n_steps} trading steps...")
    seed_numpy(seed)

    # Generate realistic market conditions
    market_returns = []
    phases = []

    for i in range(n_steps):
        # Simulate regime changes
        if i < n_steps // 3:
            # Stable period
            ret = np.random.normal(0.001, 0.015)
            phase = "stable"
        elif i < 2 * n_steps // 3:
            # Volatile period
            ret = np.random.normal(-0.002, 0.05)
            phase = "chaotic" if i % 3 == 0 else "transition"
        else:
            # Recovery period
            ret = np.random.normal(0.002, 0.02)
            phase = "stable"

        market_returns.append(ret)
        phases.append(phase)

    returns_array = np.array(market_returns)
    cum_returns = np.cumprod(1 + returns_array)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = (running_max - cum_returns) / (running_max + 1e-10)

    # Trading loop with integrated decision-making
    ecs_actions = []
    combined_actions = []
    prev_fe = None

    for i in range(n_steps):
        # 1. Update ECS regulator
        ecs_reg.update_stress(returns_array[: i + 1], drawdowns[i], prev_fe)
        prev_fe = ecs_reg.free_energy_proxy
        ecs_reg.adapt_parameters(context_phase=phases[i])

        # Get ECS metrics
        ecs_metrics = ecs_reg.get_metrics()

        # 2. Generate trading signal (from hypothetical market analysis)
        signal = market_returns[i] * np.random.uniform(0.8, 1.2)

        # 3. ECS decision
        ecs_action = ecs_reg.decide_action(signal, context_phase=phases[i])
        ecs_actions.append(ecs_action)

        # 4. Simulate FractalMotivationController behavior
        # In real integration, this would be:
        # motivation_decision = motivation_controller.recommend(
        #     state=[signal, ecs_metrics.stress_level, drawdowns[i]],
        #     signals={"risk_ok": not ecs_metrics.is_chronic, "PnL": cum_returns[i] - 1.0}
        # )

        # Simulated motivation decision logic
        if ecs_metrics.is_chronic:
            # During chronic stress, motivation system would recommend caution
            motivation_action = 0  # Hold
        elif phases[i] == "chaotic":
            # In chaotic phase, prefer exploration/caution
            motivation_action = 0 if abs(signal) < 0.05 else np.sign(signal)
        else:
            # Stable phase: follow signal
            motivation_action = 0 if abs(signal) < 0.02 else np.sign(signal)

        # 5. Combine decisions (integration logic)
        # Priority: Safety checks > ECS chronic > Motivation
        if ecs_metrics.risk_threshold < 0.001:
            # Emergency stop
            combined_action = 0
        elif ecs_metrics.is_chronic and abs(signal) > 0.1:
            # Chronic stress + strong signal: reduce position
            combined_action = -np.sign(signal)  # Opposite of signal
        elif ecs_action == 0 and motivation_action == 0:
            # Both say hold
            combined_action = 0
        elif ecs_action == motivation_action:
            # Agreement
            combined_action = ecs_action
        else:
            # Disagreement: use ECS for conservative bias
            combined_action = ecs_action if ecs_metrics.is_chronic else motivation_action

        combined_actions.append(combined_action)

        # 6. Log periodic status
        if i % 25 == 0:
            print(
                f"  Step {i:3d}: Phase={phases[i]:10s}, "
                f"Stress={ecs_metrics.stress_level:.4f}, "
                f"Chronic={'Yes' if ecs_metrics.is_chronic else 'No ':3s}, "
                f"Action={combined_action:2d}"
            )

    print(f"  ... {n_steps} steps completed")
    print()

    # Analyze results
    print("=" * 70)
    print("Results Analysis")
    print("=" * 70)
    print()

    # ECS metrics
    final_metrics = ecs_reg.get_metrics()
    print("ECS Regulator Final State:")
    print(f"  Stress Level: {final_metrics.stress_level:.4f}")
    print(f"  Free Energy: {final_metrics.free_energy_proxy:.4f}")
    print(f"  Risk Threshold: {final_metrics.risk_threshold:.6f}")
    print(f"  Compensatory Factor: {final_metrics.compensatory_factor:.4f}")
    print(f"  Is Chronic: {final_metrics.is_chronic}")
    print()

    # Action statistics
    def count_actions(action_list):
        unique, counts = np.unique(action_list, return_counts=True)
        action_dict = dict(zip(unique, counts))
        return {
            "sell": action_dict.get(-1, 0),
            "hold": action_dict.get(0, 0),
            "buy": action_dict.get(1, 0),
        }

    ecs_counts = count_actions(ecs_actions)
    combined_counts = count_actions(combined_actions)

    print("Action Distribution:")
    print("  ECS Only:")
    print(f"    Sells: {ecs_counts['sell']:3d} ({ecs_counts['sell'] / n_steps * 100:.1f}%)")
    print(f"    Holds: {ecs_counts['hold']:3d} ({ecs_counts['hold'] / n_steps * 100:.1f}%)")
    print(f"    Buys:  {ecs_counts['buy']:3d} ({ecs_counts['buy'] / n_steps * 100:.1f}%)")
    print()
    print("  Combined (ECS + Motivation):")
    print(
        f"    Sells: {combined_counts['sell']:3d} ({combined_counts['sell'] / n_steps * 100:.1f}%)"
    )
    print(
        f"    Holds: {combined_counts['hold']:3d} ({combined_counts['hold'] / n_steps * 100:.1f}%)"
    )
    print(f"    Buys:  {combined_counts['buy']:3d} ({combined_counts['buy'] / n_steps * 100:.1f}%)")
    print()

    # Agreement analysis
    agreements = sum(1 for e, c in zip(ecs_actions, combined_actions) if e == c)
    print(f"  Agreement Rate: {agreements / n_steps * 100:.1f}%")
    print()

    # Phase analysis
    phase_counts = {}
    for phase in ["stable", "chaotic", "transition"]:
        count = sum(1 for p in phases if p == phase)
        phase_counts[phase] = count
        print(f"  {phase.capitalize():12s} phases: {count:3d} ({count / n_steps * 100:.1f}%)")
    print()

    # Stress analysis
    stress_events = [h for h in ecs_reg.history if h["type"] == "Stress update"]
    high_stress_count = sum(
        1 for event in stress_events if event["details"]["stress"] > ecs_reg.stress_threshold
    )

    print("Stress Analysis:")
    print(
        f"  High stress events: {high_stress_count}/{len(stress_events)} "
        f"({high_stress_count / len(stress_events) * 100:.1f}%)"
    )
    print()

    # Performance simulation
    print("Performance Simulation:")
    print("  (Simulated returns based on actions)")

    strategy_returns = []
    for i, action in enumerate(combined_actions):
        if action == 1:  # Buy
            strategy_returns.append(market_returns[i])
        elif action == -1:  # Sell
            strategy_returns.append(-market_returns[i])
        else:  # Hold
            strategy_returns.append(0.0)

    strategy_returns = np.array(strategy_returns)
    total_return = np.sum(strategy_returns)
    volatility = np.std(strategy_returns)
    sharpe = (np.mean(strategy_returns) / (volatility + 1e-10)) * np.sqrt(252)

    print(f"  Total Return: {total_return:.4f} ({total_return * 100:.2f}%)")
    print(f"  Volatility: {volatility:.4f}")
    print(f"  Annualized Sharpe: {sharpe:.4f}")
    print()

    # Integration benefits
    print("=" * 70)
    print("Integration Benefits")
    print("=" * 70)
    print("""
1. Chronic Stress Detection:
   - ECS tracks cumulative stress over time
   - Motivation system can adjust exploration vs exploitation
   - Combined: Better risk-adjusted decisions

2. Context-Dependent Modulation:
   - ECS uses Kuramoto-Ricci phase info
   - Motivation uses fractal dynamics
   - Combined: Multi-scale market understanding

3. Thermodynamic Consistency:
   - ECS enforces free energy descent
   - Motivation tracks allostatic load
   - Combined: Stable long-term performance

4. Complementary Signals:
   - ECS: Bottom-up stress response
   - Motivation: Top-down goal-directed behavior
   - Combined: Balanced decision-making
    """)

    print("=" * 70)
    print("Integration demo completed successfully!")
    print("=" * 70)


def main():
    """Run integration demo."""
    simulate_integrated_trading(n_steps=100, seed=DEFAULT_SEED)


if __name__ == "__main__":
    main()
