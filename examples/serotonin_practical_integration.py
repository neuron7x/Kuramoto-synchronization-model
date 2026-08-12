#!/usr/bin/env python
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Practical Integration Examples for Serotonin Controller

This module demonstrates real-world integration patterns and best practices
for using the serotonin controller in trading systems.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tempfile

import yaml


def example_1_basic_integration():
    """Example 1: Basic integration with trading loop."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Basic Trading Loop Integration")
    print("=" * 70)

    # Import controller
    from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

    # Create config
    config = {
        "tonic_beta": 0.15,
        "phasic_beta": 0.35,
        "stress_gain": 1.0,
        "drawdown_gain": 1.2,
        "novelty_gain": 0.6,
        "stress_threshold": 0.7,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 3,
        "chronic_window": 6,
        "desensitization_rate": 0.05,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.6,
        "floor_gain": 0.8,
        "cooldown_extension": 2,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    # Simulate trading scenario
    print("\nSimulating market with high volatility...")

    for tick in range(20):
        # Simulate market stress (high volatility at ticks 5-10)
        if 5 <= tick <= 10:
            stress = 1.0
            drawdown = 0.2
            novelty = 0.5
        else:
            stress = 0.1
            drawdown = 0.0
            novelty = 0.1

        # Update controller
        result = controller.step(stress, drawdown, novelty)

        # Make trading decision based on controller state
        can_trade = controller.should_take_action(risk_level="moderate")
        position_size = controller.get_position_size_multiplier()

        if tick % 5 == 0 or result["hold"] != 0:
            print(f"\nTick {tick}:")
            print(f"  Stress: {stress:.1f}, Level: {result['level']:.3f}")
            print(f"  Can Trade: {can_trade}, Position Size: {position_size:.2%}")
            print(f"  Hold: {bool(result['hold'])}, Cooldown: {int(result['cooldown'])}")

            if result["hold"]:
                recovery = controller.estimate_recovery_time()
                print(f"  ⏸ IN HOLD - Recovery in ~{recovery} ticks")

    Path(config_path).unlink()
    print("\n✓ Example 1 complete")


def example_2_position_sizing():
    """Example 2: Dynamic position sizing based on stress."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Dynamic Position Sizing")
    print("=" * 70)

    from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

    config = {
        "tonic_beta": 0.15,
        "phasic_beta": 0.35,
        "stress_gain": 1.0,
        "drawdown_gain": 1.2,
        "novelty_gain": 0.6,
        "stress_threshold": 0.7,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 3,
        "chronic_window": 6,
        "desensitization_rate": 0.05,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.6,
        "floor_gain": 0.8,
        "cooldown_extension": 2,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    # Show how position size scales with stress
    print("\nPosition sizing under increasing stress:")
    print(f"{'Stress':<10} {'Level':<10} {'Position Size':<15} {'Status'}")
    print("-" * 50)

    for i in range(11):
        stress_level = i * 0.1
        controller.step(stress_level, 0.0, 0.0)

        multiplier = controller.get_position_size_multiplier()
        base_size = 10000  # $10k base position
        actual_size = base_size * multiplier

        status = (
            "✓ Full"
            if multiplier > 0.9
            else ("⚠ Reduced" if multiplier > 0.3 else "⏸ Hold" if multiplier > 0 else "✗ No Trade")
        )

        print(f"{stress_level:<10.1f} {controller.level:<10.3f} ${actual_size:<14.0f} {status}")

    Path(config_path).unlink()
    print("\n✓ Example 2 complete")


def example_3_risk_management():
    """Example 3: Integration with risk management system."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Risk Management Integration")
    print("=" * 70)

    from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

    config = {
        "tonic_beta": 0.15,
        "phasic_beta": 0.35,
        "stress_gain": 1.0,
        "drawdown_gain": 1.2,
        "novelty_gain": 0.6,
        "stress_threshold": 0.7,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 3,
        "chronic_window": 6,
        "desensitization_rate": 0.05,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.6,
        "floor_gain": 0.8,
        "cooldown_extension": 2,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    # Simulate trading with different risk profiles
    risk_profiles = ["conservative", "moderate", "aggressive"]

    print("\nMarket stress scenario (stress=0.6):")
    controller.step(0.6, 0.1, 0.2)

    print(f"\n{'Risk Profile':<15} {'Can Trade':<12} {'Position Size':<15} {'Recommendation'}")
    print("-" * 60)

    for profile in risk_profiles:
        can_trade = controller.should_take_action(risk_level=profile)
        position_multiplier = controller.get_position_size_multiplier()

        if can_trade and position_multiplier > 0.5:
            recommendation = "✓ Normal trading"
        elif can_trade and position_multiplier > 0.2:
            recommendation = "⚠ Reduce exposure"
        elif can_trade:
            recommendation = "⚡ Minimal positions"
        else:
            recommendation = "⏸ Hold/rest"

        print(f"{profile:<15} {str(can_trade):<12} {position_multiplier:<15.2%} {recommendation}")

    Path(config_path).unlink()
    print("\n✓ Example 3 complete")


def example_4_diagnostics():
    """Example 4: Debugging and diagnostics."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Diagnostics and Debugging")
    print("=" * 70)

    from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

    config = {
        "tonic_beta": 0.15,
        "phasic_beta": 0.35,
        "stress_gain": 1.0,
        "drawdown_gain": 1.2,
        "novelty_gain": 0.6,
        "stress_threshold": 0.7,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 3,
        "chronic_window": 6,
        "desensitization_rate": 0.05,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.6,
        "floor_gain": 0.8,
        "cooldown_extension": 2,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    # Simulate some stress
    print("\nSimulating market stress...")
    for _ in range(5):
        controller.step(0.8, 0.2, 0.3)

    # Get state summary
    print("\n" + controller.get_state_summary())

    # Validate state
    is_valid, issues = controller.validate_state()
    print(f"\nState validation: {'✓ VALID' if is_valid else '✗ INVALID'}")
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")

    # Get structured state
    state = controller.to_dict()
    print("\nStructured state:")
    for key, value in state.items():
        print(f"  {key}: {value:.3f}")

    Path(config_path).unlink()
    print("\n✓ Example 4 complete")


def example_5_batch_processing():
    """Example 5: Efficient batch processing for backtesting."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Batch Processing for Backtesting")
    print("=" * 70)

    import time

    from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

    config = {
        "tonic_beta": 0.15,
        "phasic_beta": 0.35,
        "stress_gain": 1.0,
        "drawdown_gain": 1.2,
        "novelty_gain": 0.6,
        "stress_threshold": 0.7,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 3,
        "chronic_window": 6,
        "desensitization_rate": 0.05,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.6,
        "floor_gain": 0.8,
        "cooldown_extension": 2,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    # Generate synthetic historical data
    n_steps = 1000
    stress_data = [0.5 + 0.3 * (i % 50) / 50.0 for i in range(n_steps)]
    drawdown_data = [0.1 * (i % 30) / 30.0 for i in range(n_steps)]
    novelty_data = [0.2 for _ in range(n_steps)]

    # Method 1: Loop (typical approach)
    controller.reset()
    start = time.time()
    for i in range(n_steps):
        controller.step(stress_data[i], drawdown_data[i], novelty_data[i])
    loop_time = time.time() - start

    # Method 2: Batch (optimized)
    controller.reset()
    start = time.time()
    results = controller.step_batch(stress_data, drawdown_data, novelty_data)
    batch_time = time.time() - start

    print(f"\nProcessed {n_steps} steps:")
    print(f"  Loop method:  {loop_time:.4f}s ({n_steps / loop_time:.0f} steps/sec)")
    print(f"  Batch method: {batch_time:.4f}s ({n_steps / batch_time:.0f} steps/sec)")
    print(f"  Speedup:      {loop_time / batch_time:.2f}x")

    # Show sample results
    print("\nSample results (last 5 steps):")
    for i, result in enumerate(results[-5:], start=n_steps - 5):
        print(f"  Step {i}: level={result['level']:.3f}, hold={bool(result['hold'])}")

    Path(config_path).unlink()
    print("\n✓ Example 5 complete")


def main():
    """Run all examples."""
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "SEROTONIN CONTROLLER" + " " * 33 + "║")
    print("║" + " " * 12 + "Practical Integration Examples" + " " * 26 + "║")
    print("╚" + "=" * 68 + "╝")

    try:
        example_1_basic_integration()
        example_2_position_sizing()
        example_3_risk_management()
        example_4_diagnostics()
        example_5_batch_processing()

        print("\n" + "=" * 70)
        print("✅ ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\nKey Takeaways:")
        print("  1. Use should_take_action() for go/no-go trading decisions")
        print("  2. Use get_position_size_multiplier() for dynamic position sizing")
        print("  3. Use estimate_recovery_time() for planning and UI updates")
        print("  4. Use validate_state() for debugging and monitoring")
        print("  5. Use step_batch() for efficient backtesting")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
