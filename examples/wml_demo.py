"""Example demonstration of WML adaptive optimization in TradePulse.

This example shows how to integrate WML into hot paths for adaptive optimization.
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.hooks_wml import make_wml, step_hot_path

# Set up environment for demo
os.environ["TP_WML_ENABLED"] = "true"
os.environ["TP_WML_GAMMA_IS"] = "0.02"
os.environ["TP_WML_EPS"] = "0.03"


def risk_freeze_check() -> bool:
    """Check if system should freeze optimization.

    In a real system, this would check:
    - EWS (Early Warning System) state == KILL
    - Expected Shortfall > limit
    - Other risk conditions
    """
    # For demo, never freeze
    return False


def simulate_feature_computation():
    """Simulate a feature computation hot path."""
    # Simulate some work
    x = 0
    for i in range(1000):
        x += i * 0.001
    return x


def main():
    """Demonstrate WML integration."""
    print("=" * 70)
    print("WML (Weighted Myelin Layer) Adaptive Optimization Demo")
    print("=" * 70)
    print()

    # Create WML instance
    print("Initializing WML with risk freeze check...")
    wml = make_wml(risk_freeze_fn=risk_freeze_check)
    print("✓ WML initialized")
    print()

    # Simulate hot path iterations
    print("Simulating hot path iterations...")
    print("-" * 70)

    for iteration in range(10):
        print(f"\nIteration {iteration + 1}:")

        # Wrap the hot path with WML
        applied = step_hot_path(
            wml,
            path="feature_pipe",
            fn=simulate_feature_computation,
            is_bp=0.0,  # No IS for feature computation
        )

        if applied:
            print("  ✓ WML applied optimization")
        else:
            print("  - WML skipped (no improvement or frozen)")

        # Check state
        state = wml.state.get("feature_pipe")
        if state:
            print(f"  Myelin level: {state.myelin:.3f}")
            print(f"  Regime: {state.last_regime.name if state.last_regime else 'UNKNOWN'}")

        # Small delay between iterations
        time.sleep(0.1)

    print()
    print("-" * 70)
    print()

    # Show audit log
    if wml.audit:
        logs = wml.audit.get_logs()
        print(f"Audit Log Summary: {len(logs)} events recorded")
        print()

        # Show first few events
        for i, log in enumerate(logs[:3]):
            print(f"Event {i + 1}:")
            print(f"  Type: {log['event']}")
            print(f"  Path: {log['data'].get('path', 'N/A')}")
            if "F_now" in log["data"]:
                print(f"  Free Energy: {log['data']['F_now']:.2f} → {log['data']['F_try']:.2f}")
            print()

    print("=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
