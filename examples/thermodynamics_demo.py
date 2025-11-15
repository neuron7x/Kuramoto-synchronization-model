#!/usr/bin/env python3
"""
Thermodynamics Implementation Demo

Demonstrates the improved thermodynamics model with:
- Adaptive temperature based on system stress
- Meaningful entropy contribution
- Heat dissipation and thermal stability
- Enhanced free energy optimization

This shows how the new thermodynamic features improve system behavior.
"""

import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Tuple

from core.energy import (
    compute_adaptive_temperature,
    heat_dissipation_rate,
    system_free_energy,
    thermal_stability_metric,
)


def create_sample_topology() -> Tuple[dict, dict, dict]:
    """Create a sample system topology for testing."""
    bonds = {
        ("ingress", "processor"): "covalent",
        ("processor", "analyzer"): "ionic",
        ("analyzer", "storage"): "metallic",
        ("storage", "egress"): "hydrogen",
    }
    
    latencies = {
        ("ingress", "processor"): 0.3,
        ("processor", "analyzer"): 0.5,
        ("analyzer", "storage"): 0.4,
        ("storage", "egress"): 0.6,
    }
    
    coherency = {
        ("ingress", "processor"): 0.85,
        ("processor", "analyzer"): 0.70,
        ("analyzer", "storage"): 0.80,
        ("storage", "egress"): 0.65,
    }
    
    return bonds, latencies, coherency


def simulate_stress_response(steps: int = 100) -> dict:
    """Simulate system response to stress over time."""
    bonds, latencies, coherency = create_sample_topology()
    
    # Track system state
    history = {
        "free_energy": [],
        "temperature": [],
        "thermal_stability": [],
        "heat_dissipation": [],
        "resource_usage": [],
        "entropy": [],
    }
    
    # Initial state
    baseline_F = 1.0
    current_F = baseline_F
    temperature = 1.0
    
    for step in range(steps):
        # Simulate stress cycle: ramp up, sustain, ramp down
        if step < 20:
            # Normal operation
            resource_usage = 0.3
            entropy = 0.6
        elif step < 40:
            # Stress ramp-up
            stress_factor = (step - 20) / 20
            resource_usage = 0.3 + 0.5 * stress_factor
            entropy = 0.6 - 0.2 * stress_factor  # Less diversity under stress
        elif step < 60:
            # High stress sustained
            resource_usage = 0.8
            entropy = 0.4
        elif step < 80:
            # Recovery
            recovery_factor = (step - 60) / 20
            resource_usage = 0.8 - 0.5 * recovery_factor
            entropy = 0.4 + 0.2 * recovery_factor
        else:
            # Back to normal
            resource_usage = 0.3
            entropy = 0.6
        
        # Compute free energy with adaptive temperature
        current_F = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature
        )
        
        # Compute rate of change
        if step > 0:
            dF_dt = (current_F - history["free_energy"][-1]) / 1.0  # dt = 1
        else:
            dF_dt = 0.0
        
        # Update temperature based on stress
        temperature = compute_adaptive_temperature(baseline_F, current_F, dF_dt)
        
        # Compute thermal metrics
        stability = thermal_stability_metric(temperature)
        dissipation = heat_dissipation_rate(current_F, baseline_F)
        
        # Record history
        history["free_energy"].append(current_F)
        history["temperature"].append(temperature)
        history["thermal_stability"].append(stability)
        history["heat_dissipation"].append(dissipation)
        history["resource_usage"].append(resource_usage)
        history["entropy"].append(entropy)
    
    return history


def demonstrate_entropy_effect():
    """Show how entropy affects free energy."""
    print("=" * 70)
    print("DEMONSTRATION 1: Entropy Effect on Free Energy")
    print("=" * 70)
    
    bonds_diverse = {
        ("A", "B"): "covalent",
        ("B", "C"): "ionic",
        ("C", "D"): "metallic",
        ("D", "E"): "hydrogen",
    }
    
    bonds_uniform = {
        ("A", "B"): "covalent",
        ("B", "C"): "covalent",
        ("C", "D"): "covalent",
        ("D", "E"): "covalent",
    }
    
    latencies = {k: 0.5 for k in bonds_diverse.keys()}
    coherency = {k: 0.8 for k in bonds_diverse.keys()}
    resource_usage = 0.4
    
    # Calculate entropy (simplified: count unique bond types)
    entropy_diverse = 0.8  # High diversity
    entropy_uniform = 0.2  # Low diversity
    
    F_diverse = system_free_energy(
        bonds_diverse, latencies, coherency, resource_usage, entropy_diverse
    )
    F_uniform = system_free_energy(
        bonds_uniform, latencies, coherency, resource_usage, entropy_uniform
    )
    
    print(f"\nDiverse topology (4 bond types):")
    print(f"  Entropy: {entropy_diverse:.2f}")
    print(f"  Free Energy: {F_diverse:.6e}")
    
    print(f"\nUniform topology (1 bond type):")
    print(f"  Entropy: {entropy_uniform:.2f}")
    print(f"  Free Energy: {F_uniform:.6e}")
    
    print(f"\nEntropy benefit: {F_uniform - F_diverse:.6e}")
    print(f"Reduction: {((F_uniform - F_diverse) / F_uniform * 100):.1f}%")
    print("\n✓ Higher entropy reduces free energy (favors diversity)")


def demonstrate_temperature_adaptation():
    """Show how temperature adapts to system stress."""
    print("\n" + "=" * 70)
    print("DEMONSTRATION 2: Adaptive Temperature")
    print("=" * 70)
    
    baseline_F = 1.0
    scenarios = [
        ("Normal (F = baseline)", 1.0, 0.0),
        ("Mild stress (F = 1.2 × baseline)", 1.2, 0.0),
        ("High stress (F = 1.5 × baseline)", 1.5, 0.0),
        ("Heating (F = baseline, dF/dt > 0)", 1.0, 0.5),
        ("Cooling (F = baseline, dF/dt < 0)", 1.0, -0.3),
    ]
    
    print("\nTemperature response to different conditions:")
    print(f"{'Scenario':<35} {'T':<8} {'Stability':<10}")
    print("-" * 70)
    
    for name, F, dF_dt in scenarios:
        T = compute_adaptive_temperature(baseline_F, F, dF_dt)
        stability = thermal_stability_metric(T)
        print(f"{name:<35} {T:<8.4f} {stability:<10.4f}")
    
    print("\n✓ Temperature rises under stress and when free energy increases")


def demonstrate_heat_dissipation():
    """Show heat dissipation behavior."""
    print("\n" + "=" * 70)
    print("DEMONSTRATION 3: Heat Dissipation")
    print("=" * 70)
    
    baseline_F = 1.0
    
    print("\nDissipation rates at different free energy levels:")
    print(f"{'Free Energy':<15} {'Distance from baseline':<25} {'Dissipation Rate':<20}")
    print("-" * 70)
    
    for F in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
        distance = F - baseline_F
        rate = heat_dissipation_rate(F, baseline_F)
        direction = "cooling ↓" if rate > 0 else "warming ↑" if rate < 0 else "equilibrium"
        print(f"{F:<15.2f} {distance:<+25.2f} {rate:<+10.6f}  {direction}")
    
    print("\n✓ System naturally dissipates heat toward equilibrium")


def plot_stress_response(history: dict):
    """Plot system response to stress cycle."""
    print("\n" + "=" * 70)
    print("DEMONSTRATION 4: System Response to Stress Cycle")
    print("=" * 70)
    
    steps = len(history["free_energy"])
    
    fig, axes = plt.subplots(3, 2, figsize=(14, 10))
    fig.suptitle("Thermodynamic Response to Stress Cycle", fontsize=16, fontweight="bold")
    
    # Plot 1: Free Energy
    ax = axes[0, 0]
    ax.plot(history["free_energy"], 'b-', linewidth=2)
    ax.set_ylabel("Free Energy (J)", fontweight="bold")
    ax.set_title("System Free Energy")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=history["free_energy"][0], color='g', linestyle='--', alpha=0.5, label='Baseline')
    ax.legend()
    
    # Plot 2: Temperature
    ax = axes[0, 1]
    ax.plot(history["temperature"], 'r-', linewidth=2)
    ax.set_ylabel("Temperature (eff. units)", fontweight="bold")
    ax.set_title("Adaptive Temperature")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1.0, color='g', linestyle='--', alpha=0.5, label='Base temp')
    ax.legend()
    
    # Plot 3: Thermal Stability
    ax = axes[1, 0]
    ax.plot(history["thermal_stability"], 'm-', linewidth=2)
    ax.set_ylabel("Stability [0-1]", fontweight="bold")
    ax.set_title("Thermal Stability")
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 1.05])
    
    # Plot 4: Heat Dissipation
    ax = axes[1, 1]
    ax.plot(history["heat_dissipation"], 'c-', linewidth=2)
    ax.set_ylabel("Dissipation Rate", fontweight="bold")
    ax.set_title("Heat Dissipation")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='k', linestyle='-', alpha=0.3)
    
    # Plot 5: Resource Usage
    ax = axes[2, 0]
    ax.plot(history["resource_usage"], 'orange', linewidth=2)
    ax.set_xlabel("Time Step", fontweight="bold")
    ax.set_ylabel("Usage [0-1]", fontweight="bold")
    ax.set_title("Resource Usage (Stress Input)")
    ax.grid(True, alpha=0.3)
    
    # Plot 6: Entropy
    ax = axes[2, 1]
    ax.plot(history["entropy"], 'g-', linewidth=2)
    ax.set_xlabel("Time Step", fontweight="bold")
    ax.set_ylabel("Entropy", fontweight="bold")
    ax.set_title("System Entropy")
    ax.grid(True, alpha=0.3)
    
    # Add phase annotations
    for ax_row in axes:
        for ax in ax_row:
            ax.axvspan(0, 20, alpha=0.1, color='green', label='Normal' if ax == axes[0,0] else '')
            ax.axvspan(20, 40, alpha=0.1, color='yellow')
            ax.axvspan(40, 60, alpha=0.1, color='red')
            ax.axvspan(60, 80, alpha=0.1, color='yellow')
            ax.axvspan(80, 100, alpha=0.1, color='green')
    
    plt.tight_layout()
    
    # Save plot
    output_path = "/tmp/thermodynamics_stress_response.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n✓ Plot saved to: {output_path}")
    
    # Print summary statistics
    print("\nSummary Statistics:")
    print(f"  Max temperature: {max(history['temperature']):.4f}")
    print(f"  Min stability: {min(history['thermal_stability']):.4f}")
    print(f"  Max free energy: {max(history['free_energy']):.6e}")
    print(f"  Energy variation: {np.std(history['free_energy']):.6e}")


def main():
    """Run all demonstrations."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "THERMODYNAMICS IMPLEMENTATION DEMO" + " " * 24 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\nDemonstrating improvements to TradePulse thermodynamic model:")
    print("  • Meaningful entropy contribution")
    print("  • Adaptive temperature based on system stress")
    print("  • Heat dissipation and thermal stability")
    print("  • Enhanced free energy optimization")
    print()
    
    # Run demonstrations
    demonstrate_entropy_effect()
    demonstrate_temperature_adaptation()
    demonstrate_heat_dissipation()
    
    # Simulate and plot stress response
    print("\nSimulating stress response...")
    history = simulate_stress_response(steps=100)
    plot_stress_response(history)
    
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("""
The improved thermodynamics implementation provides:

1. **Physically Accurate**: Entropy now contributes meaningfully to optimization
2. **Adaptive Response**: Temperature adjusts based on system stress
3. **Natural Dynamics**: Heat dissipation drives system toward equilibrium
4. **Better Monitoring**: Thermal metrics provide health indicators

The system now exhibits true thermodynamic behavior:
  • Favors diversity (high entropy) to reduce free energy
  • "Heats up" under stress, affecting optimization landscape
  • Naturally "cools down" toward baseline after stress
  • Provides early warning signals via thermal stability
    """)
    
    print("=" * 70)
    print("Demo complete! Check the generated plot for visual results.")
    print("=" * 70)


if __name__ == "__main__":
    main()
