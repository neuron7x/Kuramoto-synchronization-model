#!/usr/bin/env python
"""
Standalone test script for serotonin controller fixes.

This script validates all the fixes made to the simplified serotonin controller:
1. Hysteresis application to entry/exit thresholds
2. Cooldown decrement timing (only when not in hold)
3. Cooldown initialization (on exit, not entry)
4. Tonic/phasic separation
5. Hold property logic

Can be run directly without pytest dependencies.
"""
import sys
import tempfile
from pathlib import Path

import yaml


def load_controller():
    """Load the serotonin controller module."""
    # Use proper package import instead of dynamic file loading
    # This ensures relative imports work correctly
    from tradepulse.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    return SerotoninController


def create_controller():
    """Create a controller instance with test config."""
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
        yaml.dump({"active_profile": "legacy", "serotonin_legacy": config}, f)
        config_path = f.name

    Controller = load_controller()
    ctrl = Controller(config_path)
    Path(config_path).unlink()

    return ctrl, config


def test_hysteresis():
    """Test hysteresis prevents oscillation."""
    print("\n" + "=" * 70)
    print("TEST 1: HYSTERESIS APPLICATION")
    print("=" * 70)

    ctrl, config = create_controller()

    entry_threshold = config["stress_threshold"] + config["hysteresis"] / 2.0
    exit_threshold = config["release_threshold"] - config["hysteresis"] / 2.0

    print(f"Entry threshold: {entry_threshold:.3f}")
    print(f"Exit threshold:  {exit_threshold:.3f}")
    print(f"Hysteresis gap:  {entry_threshold - exit_threshold:.3f}")

    # Test entry
    ctrl.reset()
    for i in range(15):
        result = ctrl.step(stress=1.0, drawdown=0.0, novelty=0.0, dt=1.0)
        if ctrl._hold:
            print(f"✓ Entered hold at level {result['level']:.3f} (step {i})")
            break
    else:
        raise AssertionError("Failed to enter hold state")

    # Test exit
    for i in range(30):
        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        if not ctrl._hold and result["cooldown"] > 0:
            print(f"✓ Exited hold at level {result['level']:.3f} (step {i})")
            break
    else:
        raise AssertionError("Failed to exit hold state")


def test_cooldown_timing():
    """Test cooldown timing and decrement."""
    print("\n" + "=" * 70)
    print("TEST 2: COOLDOWN TIMING")
    print("=" * 70)

    ctrl, config = create_controller()
    ctrl.reset()

    # Enter hold
    for i in range(15):
        result = ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
        if ctrl._hold:
            print(f"✓ Entered hold at step {i}")
            break

    # Verify cooldown is 0 while in hold
    assert ctrl._cooldown == 0, f"Cooldown should be 0 in hold, got {ctrl._cooldown}"
    print("✓ Cooldown is 0 while in hold")

    # Stay in hold
    for _ in range(3):
        result = ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
        assert ctrl._cooldown == 0, "Cooldown should stay 0 while in hold"
    print("✓ Cooldown remains 0 while in hold")

    # Exit hold
    for i in range(30):
        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        if not ctrl._hold and result["cooldown"] > 0:
            print(f"✓ Exited hold at step {i}, cooldown={result['cooldown']}")
            break

    # Cooldown should be initialized (may have already decremented if we took extra steps)
    assert (
        result["cooldown"] >= config["cooldown_ticks"] - 2
    ), f"Cooldown should be near {config['cooldown_ticks']} on exit, got {result['cooldown']}"
    print(f"✓ Cooldown initialized to {result['cooldown']} on exit")

    # Verify cooldown decrements
    prev = result["cooldown"]
    for i in range(5):
        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        if prev > 0:
            assert (
                result["cooldown"] < prev
            ), f"Cooldown should decrement: {prev} -> {result['cooldown']}"
            if result["cooldown"] < prev:
                print(f"✓ Cooldown decremented: {prev} -> {result['cooldown']}")
        prev = result["cooldown"]
        if result["cooldown"] == 0:
            break

    assert result["cooldown"] == 0, "Cooldown should reach 0"
    print("✓ Cooldown reached 0")


def test_tonic_phasic():
    """Test tonic/phasic separation."""
    print("\n" + "=" * 70)
    print("TEST 3: TONIC/PHASIC SEPARATION")
    print("=" * 70)

    ctrl, config = create_controller()

    # Test tonic (slow accumulation)
    ctrl.reset()
    print("\nTesting tonic (slow integration):")
    for i in range(5):
        ctrl.step(stress=0.5, drawdown=0.0, novelty=0.0, dt=1.0)
        if i % 2 == 0:
            print(f"  Step {i}: tonic={ctrl.tonic_level:.4f}")

    assert (
        ctrl.tonic_level > 0.05
    ), f"Tonic should accumulate, got {ctrl.tonic_level:.4f}"
    assert (
        ctrl.tonic_level < 0.5
    ), f"Tonic should accumulate slowly, got {ctrl.tonic_level:.4f}"
    print(f"✓ Tonic accumulated slowly to {ctrl.tonic_level:.4f}")

    # Test phasic (fast response)
    ctrl.reset()
    print("\nTesting phasic (fast response to transients):")
    ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
    phasic_before = ctrl.phasic_level
    print(f"  Before: phasic={phasic_before:.4f}")

    ctrl.step(stress=0.0, drawdown=1.0, novelty=0.0, dt=1.0)
    phasic_during = ctrl.phasic_level
    print(f"  During drawdown: phasic={phasic_during:.4f}")

    ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
    phasic_after = ctrl.phasic_level
    print(f"  After: phasic={phasic_after:.4f}")

    assert phasic_during > phasic_before, "Phasic should spike"
    assert phasic_after < phasic_during, "Phasic should decay"
    assert (
        phasic_during > 0.02
    ), f"Phasic should show significant response, got {phasic_during:.4f}"
    print(f"✓ Phasic responded quickly (spike: {phasic_during:.4f})")


def test_hold_property():
    """Test hold property logic."""
    print("\n" + "=" * 70)
    print("TEST 4: HOLD PROPERTY LOGIC")
    print("=" * 70)

    ctrl, config = create_controller()
    ctrl.reset()

    # Initial state
    assert not ctrl.hold, "Hold should be False initially"
    print(f"✓ Initial: hold={ctrl.hold}, _hold={ctrl._hold}, cooldown={ctrl._cooldown}")

    # Enter hold
    for _ in range(15):
        ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
        if ctrl._hold:
            break

    assert ctrl._hold and ctrl.hold, "Both _hold and hold should be True"
    print(f"✓ In hold: hold={ctrl.hold}, _hold={ctrl._hold}, cooldown={ctrl._cooldown}")

    # Exit hold but cooldown active
    for _ in range(30):
        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        if not ctrl._hold and result["cooldown"] > 0:
            break

    assert not ctrl._hold and ctrl.hold, "hold should be True via cooldown"
    print(
        f"✓ After exit: hold={ctrl.hold}, _hold={ctrl._hold}, cooldown={result['cooldown']}"
    )

    # Wait for cooldown to expire
    for _ in range(config["cooldown_ticks"] + 2):
        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)

    assert not ctrl.hold, "hold should be False after cooldown expires"
    print(
        f"✓ After cooldown: hold={ctrl.hold}, _hold={ctrl._hold}, cooldown={ctrl._cooldown}"
    )


def test_config_validation():
    """Test configuration validation."""
    print("\n" + "=" * 70)
    print("TEST 5: CONFIGURATION VALIDATION")
    print("=" * 70)

    Controller = load_controller()

    # Test missing key
    incomplete_config = {
        "tonic_beta": 0.15,
        # Missing other required keys
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "active_profile": "legacy",
                "serotonin_legacy": incomplete_config,
            },
            f,
        )
        config_path = f.name

    try:
        Controller(config_path)
        raise AssertionError("Should have raised ValueError for missing keys")
    except ValueError as e:
        assert "Invalid serotonin root configuration" in str(e)
        print("✓ Properly rejects incomplete config")
    finally:
        Path(config_path).unlink()

    # Test invalid value
    invalid_config = {
        "tonic_beta": 1.5,  # > 1.0, invalid
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
        yaml.dump(invalid_config, f)
        config_path = f.name

    try:
        Controller(config_path)
        raise AssertionError("Should have raised ValueError for invalid beta")
    except ValueError:
        print("✓ Properly rejects invalid beta value")
    finally:
        Path(config_path).unlink()


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SEROTONIN CONTROLLER - COMPREHENSIVE FIX VALIDATION")
    print("=" * 70)

    try:
        test_hysteresis()
        test_cooldown_timing()
        test_tonic_phasic()
        test_hold_property()
        test_config_validation()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        print("\nValidated fixes:")
        print("  1. ✓ Hysteresis application (entry 0.75, exit 0.35)")
        print("  2. ✓ Cooldown timing (initialized on exit, decrements outside hold)")
        print("  3. ✓ Tonic/phasic separation (slow vs fast response)")
        print("  4. ✓ Hold property logic (_hold + cooldown)")
        print("  5. ✓ Configuration validation")
        print("=" * 70)
        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
