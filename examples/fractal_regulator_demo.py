"""Demo script showcasing the EEPFractalRegulator capabilities.

This script demonstrates:
1. Basic regulator usage with market-like data
2. Crisis detection during volatile periods
3. Metrics evolution over time
4. Integration patterns
"""

from __future__ import annotations

import numpy as np

# Direct import to avoid module dependencies
from core.neuro.fractal_regulator import EEPFractalRegulator
from core.utils.determinism import DEFAULT_SEED


def demo_basic_usage():
    """Demonstrate basic regulator usage."""
    print("=" * 60)
    print("DEMO 1: Basic Usage")
    print("=" * 60)

    regulator = EEPFractalRegulator(window_size=50, seed=DEFAULT_SEED)

    # Simulate a few market signals
    signals = [0.1, -0.05, 0.15, 0.02, -0.08]

    for i, signal in enumerate(signals, 1):
        metrics = regulator.update_state(signal)
        print(f"\nStep {i}: signal={signal:+.2f}")
        print(f"  Hurst:         {metrics.hurst:.3f}")
        print(f"  PLE:           {metrics.ple:.3f}")
        print(f"  CSI:           {metrics.csi:.3f}")
        print(f"  Energy Cost:   {metrics.energy_cost:.3f}")
        print(f"  Efficiency Δ:  {metrics.efficiency_delta:+.3f}")


def demo_crisis_detection():
    """Demonstrate crisis detection with volatile data."""
    print("\n" + "=" * 60)
    print("DEMO 2: Crisis Detection")
    print("=" * 60)

    regulator = EEPFractalRegulator(
        window_size=100, crisis_threshold=0.4, seed=DEFAULT_SEED
    )

    rng = np.random.default_rng(DEFAULT_SEED)

    # Phase 1: Stable market
    print("\nPhase 1: Stable Market (σ=0.01)")
    stable_signals = rng.normal(0, 0.01, 50)
    for signal in stable_signals:
        regulator.update_state(signal)

    stable_csi = regulator.compute_csi()
    print(f"  CSI: {stable_csi:.3f}")
    print(f"  Crisis: {regulator.is_in_crisis()}")

    # Phase 2: Volatile market (crisis)
    print("\nPhase 2: Volatile Market (σ=3.0)")
    volatile_signals = rng.normal(0, 3.0, 50)
    for signal in volatile_signals:
        regulator.update_state(signal)

    volatile_csi = regulator.compute_csi()
    print(f"  CSI: {volatile_csi:.3f}")
    print(f"  Crisis: {regulator.is_in_crisis()}")


def demo_trade_cycle_simulation():
    """Demonstrate full trade cycle simulation."""
    print("\n" + "=" * 60)
    print("DEMO 3: Trade Cycle Simulation")
    print("=" * 60)

    regulator = EEPFractalRegulator(window_size=100, seed=DEFAULT_SEED)
    rng = np.random.default_rng(DEFAULT_SEED)

    # Create market-like returns: stable → crisis → recovery
    stable = rng.normal(0, 0.01, 50)
    crisis = rng.normal(0, 0.05, 30)
    recovery = rng.normal(0, 0.01, 20)
    signals = np.concatenate([stable, crisis, recovery])

    print(f"\nSimulating {len(signals)} trading periods...")
    results = regulator.simulate_trade_cycle(signals)

    # Analyze results
    crisis_periods = [i for i, m in enumerate(results) if m.csi < 0.4]

    print("\nResults:")
    print(f"  Total periods:     {len(results)}")
    print(f"  Crisis periods:    {len(crisis_periods)}")
    print(f"  Crisis ratio:      {len(crisis_periods) / len(results) * 100:.1f}%")
    print(f"  Avg Hurst:         {np.mean([m.hurst for m in results]):.3f}")
    print(f"  Avg CSI:           {np.mean([m.csi for m in results]):.3f}")
    print(f"  Min CSI:           {min(m.csi for m in results):.3f}")
    print(f"  Max CSI:           {max(m.csi for m in results):.3f}")

    # Show crisis periods
    if crisis_periods:
        print(f"\nCrisis detected at periods: {crisis_periods[:10]}...")


def demo_parameter_sensitivity():
    """Demonstrate sensitivity to threshold parameter."""
    print("\n" + "=" * 60)
    print("DEMO 4: Parameter Sensitivity")
    print("=" * 60)

    rng = np.random.default_rng(DEFAULT_SEED)
    signals = rng.normal(0, 1.0, 100)

    thresholds = [0.2, 0.3, 0.4, 0.5]

    print("\nTesting different crisis thresholds:")
    for threshold in thresholds:
        regulator = EEPFractalRegulator(
            window_size=100, crisis_threshold=threshold, seed=DEFAULT_SEED
        )

        results = regulator.simulate_trade_cycle(signals)
        crisis_count = sum(1 for m in results if m.csi < threshold)

        print(
            f"  Threshold {threshold:.1f}: {crisis_count:3d} crisis periods "
            f"({crisis_count / len(results) * 100:.1f}%)"
        )


def demo_integration_pattern():
    """Demonstrate integration pattern for analytics pipeline."""
    print("\n" + "=" * 60)
    print("DEMO 5: Integration Pattern")
    print("=" * 60)

    class MarketHealthMonitor:
        """Example integration: monitor market health."""

        def __init__(self):
            self.regulator = EEPFractalRegulator(window_size=50, crisis_threshold=0.3)
            self.alerts = []

        def process_return(self, return_value: float) -> dict:
            """Process a market return and check health."""
            metrics = self.regulator.update_state(return_value)

            status = {
                "return": return_value,
                "hurst": metrics.hurst,
                "csi": metrics.csi,
                "in_crisis": self.regulator.is_in_crisis(),
            }

            if status["in_crisis"]:
                self.alerts.append(status)

            return status

    # Simulate usage
    monitor = MarketHealthMonitor()
    rng = np.random.default_rng(DEFAULT_SEED)

    print("\nMonitoring market returns...")
    returns = np.concatenate(
        [
            rng.normal(0, 0.01, 30),  # Stable
            rng.normal(0, 0.08, 20),  # Volatile
        ]
    )

    for ret in returns:
        monitor.process_return(ret)

    print(f"  Total returns processed: {len(returns)}")
    print(f"  Crisis alerts:           {len(monitor.alerts)}")
    if monitor.alerts:
        print(f"  First alert at return:   {monitor.alerts[0]['return']:.4f}")
        print(f"  First alert CSI:         {monitor.alerts[0]['csi']:.3f}")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("EEPFractalRegulator Demonstration")
    print("=" * 60)

    demo_basic_usage()
    demo_crisis_detection()
    demo_trade_cycle_simulation()
    demo_parameter_sensitivity()
    demo_integration_pattern()

    print("\n" + "=" * 60)
    print("All demos completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
