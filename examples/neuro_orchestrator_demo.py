#!/usr/bin/env python
"""Demo script for the Neuro-Orchestrator Agent.

This script demonstrates how to use the NeuroOrchestrator to generate
module-level instructions for different trading scenarios.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for standalone execution
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import directly from module to avoid triggering full app initialization
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "neuro_orchestrator",
    src_path / "tradepulse" / "core" / "neuro" / "neuro_orchestrator.py",
)
neuro_orchestrator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(neuro_orchestrator)

NeuroOrchestrator = neuro_orchestrator.NeuroOrchestrator
TradingScenario = neuro_orchestrator.TradingScenario
create_orchestration_from_scenario = (
    neuro_orchestrator.create_orchestration_from_scenario
)


def demo_basic_usage():
    """Demonstrate basic orchestrator usage."""
    print("=" * 80)
    print("DEMO 1: Basic Orchestrator Usage")
    print("=" * 80)

    # Create a trading scenario
    scenario = TradingScenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
        capital=100000.0,
        max_position_size=0.2,
    )

    # Initialize orchestrator
    orchestrator = NeuroOrchestrator(
        free_energy_threshold=1.4,
        enable_tacl_validation=True,
    )

    # Generate orchestration
    output = orchestrator.orchestrate(scenario)

    # Display JSON output
    print("\nGenerated Orchestration (JSON):")
    print(output.to_json())
    print()


def demo_risk_profiles():
    """Demonstrate different risk profiles."""
    print("=" * 80)
    print("DEMO 2: Different Risk Profiles")
    print("=" * 80)

    profiles = ["conservative", "moderate", "aggressive"]

    for profile in profiles:
        print(f"\n{profile.upper()} Profile:")
        print("-" * 40)

        output = create_orchestration_from_scenario(
            market="ETH/USDT",
            timeframe="5m",
            risk_profile=profile,
        )

        print(f"Learning Rate: {output.parameters['learning_rate']}")
        print(f"Discount Gamma: {output.parameters['discount_gamma']}")
        print(f"Exposure Limit: {output.parameters['exposure_limit']}")
        print(f"Temperature: {output.parameters['temperature']}")
        print(f"Threat Threshold: {output.risk_contour.threat_threshold}")
        print(f"Drawdown Limit: {output.risk_contour.drawdown_limit}")


def demo_module_sequence():
    """Demonstrate module sequence structure."""
    print("\n" + "=" * 80)
    print("DEMO 3: Module Execution Sequence")
    print("=" * 80)

    output = create_orchestration_from_scenario(
        market="SOL/USDT",
        timeframe="15m",
        risk_profile="moderate",
    )

    print("\nModule Execution Order (Biological Pathway):")
    print("-" * 40)

    for i, module in enumerate(output.module_sequence, 1):
        print(f"\n{i}. {module.module_name.upper()}")
        print(f"   Operation: {module.operation}")
        print(f"   Priority: {module.priority}")
        print(f"   Parameters: {module.parameters}")


def demo_neuromodulator_config():
    """Demonstrate neuromodulator configuration."""
    print("\n" + "=" * 80)
    print("DEMO 4: Neuromodulator Configuration")
    print("=" * 80)

    output = create_orchestration_from_scenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
    )

    print("\nNeuromodulator Settings:")
    print("-" * 40)

    # Dopamine (reward prediction)
    print("\nDOPAMINE (Action Selection & Learning):")
    for key, value in output.parameters["dopamine"].items():
        print(f"  {key}: {value}")

    # Serotonin (stress response)
    print("\nSEROTONIN (Stress & Risk Management):")
    for key, value in output.parameters["serotonin"].items():
        print(f"  {key}: {value}")

    # GABA (inhibition)
    print("\nGABA (Impulse Inhibition):")
    for key, value in output.parameters["gaba"].items():
        print(f"  {key}: {value}")

    # NA/ACh (arousal/attention)
    print("\nNA/ACh (Arousal & Attention):")
    for key, value in output.parameters["na_ach"].items():
        print(f"  {key}: {value}")


def demo_tacl_integration():
    """Demonstrate TACL integration."""
    print("\n" + "=" * 80)
    print("DEMO 5: TACL (Thermodynamic Autonomic Control Layer)")
    print("=" * 80)

    output = create_orchestration_from_scenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
    )

    print("\nTACL Configuration:")
    print("-" * 40)

    tacl_config = output.parameters["tacl"]
    print(f"Monotonic Descent Enforced: {tacl_config['monotonic_descent']}")
    print(f"Free Energy Threshold: {output.parameters['free_energy_threshold']}")
    print(f"Epsilon Tolerance: {tacl_config['epsilon_tolerance']}")
    print(f"Crisis Detection: {tacl_config['crisis_detection']}")
    print(f"Protocol Options: {', '.join(tacl_config['protocol_options'])}")

    print("\nTACL ensures:")
    print(
        "  • Monotonic free-energy descent (no action increases system F without override)"
    )
    print("  • Hot-swapping of communication protocols (RDMA, CRDT, gRPC, etc.)")
    print("  • Crisis-aware adaptive recovery")
    print("  • 7-year audit trail for compliance")


def demo_learning_loop():
    """Demonstrate learning loop configuration."""
    print("\n" + "=" * 80)
    print("DEMO 6: Dopamine Learning Loop (TD-based)")
    print("=" * 80)

    output = create_orchestration_from_scenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
    )

    print("\nLearning Loop Specification:")
    print("-" * 40)

    loop = output.learning_loop
    print(f"Algorithm: {loop.algorithm}")
    print(f"Discount Gamma (γ): {loop.discount_gamma}")
    print(f"Learning Rate (α): {loop.learning_rate}")
    print(f"Prediction Window: {loop.prediction_window} step(s)")
    print(f"Error Metric: {loop.error_metric}")
    print("\nUpdate Rule:")
    print(f"  {loop.update_rule}")

    print("\nBiological Mapping:")
    print("  Dopamine → Reward Prediction Error (RPE)")
    print("  TD(0) → Phasic dopamine burst on unexpected reward")
    print("  Value update → Synaptic plasticity in basal ganglia")


def demo_custom_parameters():
    """Demonstrate custom parameter overrides."""
    print("\n" + "=" * 80)
    print("DEMO 7: Custom Parameter Overrides")
    print("=" * 80)

    scenario = TradingScenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
    )

    custom_params = {
        "learning_rate": 0.025,
        "temperature": 1.5,
        "dopamine": {
            "burst_factor": 2.0,
            "decay_rate": 0.90,
            "invigoration_threshold": 0.7,
        },
    }

    orchestrator = NeuroOrchestrator()
    output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)

    print("\nCustom Parameters Applied:")
    print("-" * 40)
    print(f"Learning Rate: {output.parameters['learning_rate']}")
    print(f"Temperature: {output.parameters['temperature']}")
    print(f"Dopamine Burst Factor: {output.parameters['dopamine']['burst_factor']}")
    print(f"Dopamine Decay Rate: {output.parameters['dopamine']['decay_rate']}")


def demo_validation_constraints():
    """Demonstrate TACL validation constraints."""
    print("\n" + "=" * 80)
    print("DEMO 8: TACL Validation Constraints")
    print("=" * 80)

    scenario = TradingScenario(
        market="BTC/USDT",
        timeframe="1h",
        risk_profile="moderate",
    )

    orchestrator = NeuroOrchestrator(enable_tacl_validation=True)

    # Valid configuration
    print("\nAttempting valid configuration...")
    try:
        output = orchestrator.orchestrate(scenario)
        print("✓ Valid configuration accepted")
        print(f"  Free Energy Threshold: {output.parameters['free_energy_threshold']}")
    except ValueError as e:
        print(f"✗ Configuration rejected: {e}")

    # Invalid: high free-energy threshold
    print("\nAttempting invalid configuration (high free-energy threshold)...")
    try:
        invalid_params = {"free_energy_threshold": 2.5}
        output = orchestrator.orchestrate(scenario, custom_parameters=invalid_params)
        print("✗ Invalid configuration should have been rejected!")
    except ValueError as e:
        print(f"✓ Configuration correctly rejected: {e}")

    # Invalid: high temperature
    print("\nAttempting invalid configuration (excessive temperature)...")
    try:
        invalid_params = {"temperature": 3.0}
        output = orchestrator.orchestrate(scenario, custom_parameters=invalid_params)
        print("✗ Invalid configuration should have been rejected!")
    except ValueError as e:
        print(f"✓ Configuration correctly rejected: {e}")

    # Invalid: disabled monotonic descent
    print("\nAttempting invalid configuration (monotonic descent disabled)...")
    try:
        invalid_params = {"tacl": {"monotonic_descent": False}}
        output = orchestrator.orchestrate(scenario, custom_parameters=invalid_params)
        print("✗ Invalid configuration should have been rejected!")
    except ValueError as e:
        print(f"✓ Configuration correctly rejected: {e}")


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  Neuro-Orchestrator Agent for TradePulse".center(78) + "║")
    print("║" + "  Biologically-Inspired Module Coordination Demo".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    demo_basic_usage()
    demo_risk_profiles()
    demo_module_sequence()
    demo_neuromodulator_config()
    demo_tacl_integration()
    demo_learning_loop()
    demo_custom_parameters()
    demo_validation_constraints()

    print("\n" + "=" * 80)
    print("All demos completed successfully!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("  1. Orchestrator maps trading scenarios to neuroscience-inspired modules")
    print("  2. Basal ganglia → action selection with neuromodulators")
    print("  3. Dopamine loop → TD-based reinforcement learning")
    print("  4. Threat contours → risk management and VaR/ES")
    print("  5. TACL → monotonic free-energy descent with protocol hot-swapping")
    print("  6. JSON output format for module-level instructions")
    print("  7. Validation ensures thermodynamic stability constraints")
    print()


if __name__ == "__main__":
    main()
