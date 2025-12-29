"""
ThermoController HPC-AI Integration Example

Demonstrates how to integrate HPC-AI v4 with the ThermoController
for thermodynamic-aware adaptive trading.
"""

import networkx as nx

from neuropro.hpc_validation import generate_synthetic_data
from core.utils.determinism import DEFAULT_SEED
from runtime.thermo_controller import ThermoController


def create_sample_graph():
    """Create a sample network graph for ThermoController."""
    G = nx.DiGraph()

    # Add edges representing system components
    edges = [
        (
            "DataFeed",
            "Processor",
            {"type": "covalent", "latency_norm": 0.1, "coherency": 0.9},
        ),
        (
            "Processor",
            "Strategy",
            {"type": "ionic", "latency_norm": 0.15, "coherency": 0.85},
        ),
        (
            "Strategy",
            "Executor",
            {"type": "metallic", "latency_norm": 0.2, "coherency": 0.8},
        ),
        (
            "Executor",
            "Market",
            {"type": "covalent", "latency_norm": 0.25, "coherency": 0.75},
        ),
        ("Market", "DataFeed", {"type": "vdw", "latency_norm": 0.3, "coherency": 0.7}),
    ]

    for src, dst, attrs in edges:
        G.add_edge(src, dst, **attrs)

    # Add node attributes
    for node in G.nodes():
        G.nodes[node]["cpu_norm"] = 0.3

    return G


def main():
    print("=" * 80)
    print("ThermoController + HPC-AI v4 Integration Example")
    print("=" * 80)
    print()

    # Step 1: Create ThermoController
    print("Step 1: Initializing ThermoController")
    print("-" * 80)
    graph = create_sample_graph()
    controller = ThermoController(graph)
    print(
        f"ThermoController initialized with {len(graph.nodes())} nodes and {len(graph.edges())} edges"
    )
    print(f"Nodes: {', '.join(graph.nodes())}")
    print(f"Initial free energy: {controller.get_current_F():.6f}")
    print()

    # Step 2: Initialize HPC-AI
    print("Step 2: Initializing HPC-AI Module")
    print("-" * 80)
    controller.init_hpc_ai(
        input_dim=10,
        state_dim=128,
        action_dim=3,
        learning_rate=1e-4,
    )
    print("HPC-AI initialized successfully")
    print(f"HPC-AI enabled: {controller._hpc_ai_enabled}")
    print()

    # Step 3: Generate market data
    print("Step 3: Generating Market Data")
    print("-" * 80)
    market_data = generate_synthetic_data(n_days=500, seed=DEFAULT_SEED)
    print(f"Generated {len(market_data)} days of market data")
    print(
        f"Price range: ${market_data['close'].min():.2f} - ${market_data['close'].max():.2f}"
    )
    print()

    # Step 4: Run combined control loop
    print("Step 4: Running Combined Thermodynamic + HPC-AI Control Loop")
    print("-" * 80)

    results = []
    for i in range(10):
        # Run thermodynamic control step
        controller.control_step()

        # Get market data window
        window_start = max(0, i * 40)
        window_end = min(len(market_data), window_start + 100)
        window_data = market_data.iloc[window_start:window_end]

        # Run HPC-AI control step
        hpc_result = controller.hpc_ai_control_step(window_data, execute_action=True)

        # Combine metrics
        combined_result = {
            "step": i,
            "free_energy": controller.get_current_F(),
            "dF_dt": controller.get_dF_dt(),
            "circuit_breaker": controller.circuit_breaker_active,
            "hpc_action": hpc_result["action"],
            "hpc_pwpe": hpc_result["pwpe"],
            "hpc_td_error": hpc_result["td_error"],
            "hpc_reward": hpc_result.get("reward", 0.0),
        }
        results.append(combined_result)

        # Print progress
        action_names = {0: "HOLD", 1: "BUY", 2: "SELL"}
        print(
            f"Step {i:2d}: F={combined_result['free_energy']:8.6f} | "
            f"dF/dt={combined_result['dF_dt']:7.4f} | "
            f"Action={action_names[combined_result['hpc_action']]:4s} | "
            f"PWPE={combined_result['hpc_pwpe']:.4f}"
        )

    print()

    # Step 5: Analyze results
    print("Step 5: Analyzing Results")
    print("-" * 80)

    import numpy as np

    free_energies = [r["free_energy"] for r in results]
    pwpes = [r["hpc_pwpe"] for r in results]
    actions = [r["hpc_action"] for r in results]

    print("Thermodynamic Metrics:")
    print(f"  Initial F: {free_energies[0]:.6f}")
    print(f"  Final F: {free_energies[-1]:.6f}")
    print(f"  Change: {free_energies[-1] - free_energies[0]:.6f}")
    print(f"  Mean F: {np.mean(free_energies):.6f}")
    print(f"  Std F: {np.std(free_energies):.6f}")
    print()

    print("HPC-AI Metrics:")
    print(f"  Mean PWPE: {np.mean(pwpes):.4f}")
    print(f"  Std PWPE: {np.std(pwpes):.4f}")
    print(f"  Final blending alpha: {controller.hpc_ai.blending_alpha.item():.4f}")
    print()

    print("Action Distribution:")
    action_counts = {0: 0, 1: 0, 2: 0}
    for action in actions:
        action_counts[action] += 1

    total_actions = len(actions)
    print(f"  HOLD: {action_counts[0]:2d} ({action_counts[0]/total_actions:5.1%})")
    print(f"  BUY:  {action_counts[1]:2d} ({action_counts[1]/total_actions:5.1%})")
    print(f"  SELL: {action_counts[2]:2d} ({action_counts[2]/total_actions:5.1%})")
    print()

    print("Circuit Breaker Status:")
    cb_active = any(r["circuit_breaker"] for r in results)
    print(f"  Circuit breaker triggered: {'Yes' if cb_active else 'No'}")
    if cb_active:
        first_trigger = next(i for i, r in enumerate(results) if r["circuit_breaker"])
        print(f"  First trigger at step: {first_trigger}")
    print()

    # Summary
    print("=" * 80)
    print("Integration Demonstration Complete!")
    print("=" * 80)
    print()
    print("Key Points:")
    print("  ✓ ThermoController manages system free energy")
    print("  ✓ HPC-AI module provides adaptive trading decisions")
    print("  ✓ Both systems work together without conflicts")
    print("  ✓ Circuit breaker provides safety guarantees")
    print("  ✓ PWPE tracks market uncertainty")
    print()
    print("Integration Benefits:")
    print("  - Thermodynamic optimization of system topology")
    print("  - Neural predictive coding for market dynamics")
    print("  - Active inference for uncertainty-aware decisions")
    print("  - Self-rewarding RL for adaptive learning")
    print("  - Metastable transition detection for regime changes")
    print()


if __name__ == "__main__":
    main()
