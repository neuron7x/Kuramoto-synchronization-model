#!/usr/bin/env python
"""
Tests for practical utility methods added to serotonin controller.

Tests the new helper methods for real-world integration:
- should_take_action()
- get_position_size_multiplier()
- estimate_recovery_time()
- validate_state()
- get_state_summary()
- step_batch()
- get_performance_stats()
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


def create_controller(enable_perf=False):
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
        yaml.dump(
            {"active_profile": "legacy", "serotonin_legacy": config},
            f,
        )
        config_path = f.name

    Controller = load_controller()
    ctrl = Controller(config_path, enable_performance_tracking=enable_perf)
    Path(config_path).unlink()

    return ctrl


def test_should_take_action():
    """Test should_take_action utility method."""
    print("\n" + "=" * 70)
    print("TEST 1: should_take_action()")
    print("=" * 70)

    ctrl = create_controller()

    # Low stress - should allow actions
    ctrl.reset()
    ctrl.step(0.1, 0.0, 0.0)
    assert ctrl.should_take_action(
        "conservative"
    ), "Conservative should allow at low stress"
    assert ctrl.should_take_action("moderate"), "Moderate should allow at low stress"
    assert ctrl.should_take_action(
        "aggressive"
    ), "Aggressive should allow at low stress"
    print("✓ Low stress: all risk levels allow trading")

    # Medium stress - varies by risk level
    ctrl.reset()
    for _ in range(10):
        ctrl.step(0.5, 0.0, 0.0)

    conservative = ctrl.should_take_action("conservative")
    moderate = ctrl.should_take_action("moderate")
    aggressive = ctrl.should_take_action("aggressive")

    print(f"✓ Medium stress (level={ctrl.level:.3f}):")
    print(
        f"  Conservative: {conservative}, Moderate: {moderate}, Aggressive: {aggressive}"
    )

    # In hold - none should allow
    ctrl.reset()
    for _ in range(15):
        ctrl.step(1.0, 0.5, 0.0)
        if ctrl.hold:
            break

    assert not ctrl.should_take_action("conservative"), "Should not trade in hold"
    assert not ctrl.should_take_action("moderate"), "Should not trade in hold"
    assert not ctrl.should_take_action("aggressive"), "Should not trade in hold"
    print("✓ In hold: no risk level allows trading")


def test_position_size_multiplier():
    """Test get_position_size_multiplier utility method."""
    print("\n" + "=" * 70)
    print("TEST 2: get_position_size_multiplier()")
    print("=" * 70)

    ctrl = create_controller()

    # At zero stress - full size
    ctrl.reset()
    ctrl.step(0.0, 0.0, 0.0)
    multiplier = ctrl.get_position_size_multiplier()
    assert multiplier == 1.0, f"Should be 1.0 at zero stress, got {multiplier}"
    print(f"✓ Zero stress: multiplier = {multiplier:.2f} (full size)")

    # At threshold - should be zero
    ctrl.reset()
    for _ in range(20):
        ctrl.step(1.0, 0.0, 0.0)

    multiplier = ctrl.get_position_size_multiplier()
    assert (
        multiplier >= 0.0 and multiplier <= 0.1
    ), f"Should be near 0 at threshold, got {multiplier}"
    print(f"✓ At threshold: multiplier = {multiplier:.2f} (minimal/no size)")

    # Mid-range stress - scaled
    ctrl.reset()
    for _ in range(5):
        ctrl.step(0.3, 0.0, 0.0)

    multiplier = ctrl.get_position_size_multiplier()
    assert 0.3 < multiplier < 0.9, f"Should be scaled at mid-stress, got {multiplier}"
    print(f"✓ Mid-range stress: multiplier = {multiplier:.2f} (scaled)")

    # In hold - should be zero
    ctrl.reset()
    for _ in range(15):
        ctrl.step(1.0, 0.5, 0.0)
        if ctrl.hold:
            break

    multiplier = ctrl.get_position_size_multiplier()
    assert multiplier == 0.0, f"Should be 0 in hold, got {multiplier}"
    print(f"✓ In hold: multiplier = {multiplier:.2f} (no positions)")


def test_estimate_recovery_time():
    """Test estimate_recovery_time utility method."""
    print("\n" + "=" * 70)
    print("TEST 3: estimate_recovery_time()")
    print("=" * 70)

    ctrl = create_controller()

    # Not in hold - should be 0
    ctrl.reset()
    ctrl.step(0.1, 0.0, 0.0)
    recovery = ctrl.estimate_recovery_time()
    assert recovery == 0, f"Should be 0 when not in hold, got {recovery}"
    print(f"✓ Not in hold: recovery time = {recovery}")

    # Enter hold and check recovery estimate
    ctrl.reset()
    for _ in range(15):
        ctrl.step(1.0, 0.5, 0.0)
        if ctrl.hold:
            break

    recovery = ctrl.estimate_recovery_time()
    assert recovery > 0, f"Should have recovery time in hold, got {recovery}"
    print(f"✓ In hold: estimated recovery = {recovery} ticks")

    # In cooldown phase
    for _ in range(30):
        ctrl.step(0.0, 0.0, 0.0)
        if not ctrl._hold and ctrl._cooldown > 0:
            break

    recovery = ctrl.estimate_recovery_time()
    assert (
        recovery == ctrl._cooldown
    ), f"Should match cooldown, got {recovery} vs {ctrl._cooldown}"
    print(f"✓ In cooldown: recovery time = {recovery} (matches cooldown)")


def test_validate_state():
    """Test validate_state utility method."""
    print("\n" + "=" * 70)
    print("TEST 4: validate_state()")
    print("=" * 70)

    ctrl = create_controller()

    # Normal state should be valid
    ctrl.reset()
    for _ in range(5):
        ctrl.step(0.5, 0.1, 0.1)

    is_valid, issues = ctrl.validate_state()
    assert is_valid, f"Normal state should be valid, issues: {issues}"
    print("✓ Normal operation: state is valid")

    # Test after many steps
    for _ in range(50):
        ctrl.step(0.3, 0.05, 0.05)

    is_valid, issues = ctrl.validate_state()
    assert is_valid, f"State should remain valid after many steps, issues: {issues}"
    print("✓ After 50+ steps: state is still valid")


def test_get_state_summary():
    """Test get_state_summary utility method."""
    print("\n" + "=" * 70)
    print("TEST 5: get_state_summary()")
    print("=" * 70)

    ctrl = create_controller()
    ctrl.reset()

    # Build up some state
    for _ in range(10):
        ctrl.step(0.6, 0.1, 0.1)

    summary = ctrl.get_state_summary()

    # Check that summary contains key information
    assert "Level:" in summary, "Summary should contain level"
    assert "Hold:" in summary, "Summary should contain hold state"
    assert "Desensitization:" in summary, "Summary should contain desensitization"
    assert "Thresholds:" in summary, "Summary should contain thresholds"

    print("✓ State summary generated:")
    print(summary)


def test_step_batch():
    """Test step_batch utility method."""
    print("\n" + "=" * 70)
    print("TEST 6: step_batch()")
    print("=" * 70)

    ctrl = create_controller()
    ctrl.reset()

    # Create test sequences
    n = 10
    stress_seq = [0.5] * n
    drawdown_seq = [0.1] * n
    novelty_seq = [0.05] * n

    # Process batch
    results = ctrl.step_batch(stress_seq, drawdown_seq, novelty_seq)

    assert len(results) == n, f"Should return {n} results, got {len(results)}"
    print(f"✓ Batch processed {n} steps successfully")

    # Verify results structure
    for i, result in enumerate(results):
        assert "level" in result, f"Result {i} missing 'level'"
        assert "hold" in result, f"Result {i} missing 'hold'"
        assert "cooldown" in result, f"Result {i} missing 'cooldown'"

    print("✓ All results have correct structure")
    print(
        f"  Final state: level={results[-1]['level']:.3f}, hold={bool(results[-1]['hold'])}"
    )

    # Test error handling
    try:
        ctrl.step_batch([0.1], [0.1, 0.2], [0.1])
        assert False, "Should raise error for mismatched lengths"
    except ValueError:
        print("✓ Correctly validates input sequence lengths")


def test_performance_tracking():
    """Test performance tracking functionality."""
    print("\n" + "=" * 70)
    print("TEST 7: Performance Tracking")
    print("=" * 70)

    # Controller without tracking
    ctrl_no_track = create_controller(enable_perf=False)
    for _ in range(10):
        ctrl_no_track.step(0.5, 0.1, 0.1)

    stats = ctrl_no_track.get_performance_stats()
    assert len(stats) == 0, "Should return empty dict when tracking disabled"
    print("✓ No tracking when disabled")

    # Controller with tracking
    ctrl_track = create_controller(enable_perf=True)

    for _ in range(50):
        ctrl_track.step(0.5, 0.1, 0.1)

    stats = ctrl_track.get_performance_stats()

    assert "total_steps" in stats, "Should have total_steps"
    assert "avg_step_time_ms" in stats, "Should have avg_step_time_ms"
    assert "steps_per_second" in stats, "Should have steps_per_second"
    assert "hold_rate" in stats, "Should have hold_rate"

    assert (
        stats["total_steps"] == 50
    ), f"Should have 50 steps, got {stats['total_steps']}"
    assert stats["avg_step_time_ms"] > 0, "Should have positive step time"
    assert stats["steps_per_second"] > 0, "Should have positive throughput"

    print("✓ Performance stats collected:")
    print(f"  Total steps: {stats['total_steps']:.0f}")
    print(f"  Avg time: {stats['avg_step_time_ms']:.4f} ms/step")
    print(f"  Throughput: {stats['steps_per_second']:.0f} steps/sec")
    print(f"  Hold rate: {stats['hold_rate']:.2%}")

    # Test reset
    ctrl_track.reset_performance_stats()
    stats_after_reset = ctrl_track.get_performance_stats()
    assert len(stats_after_reset) == 0, "Should be empty after reset"
    print("✓ Performance stats reset correctly")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("PRACTICAL UTILITIES - COMPREHENSIVE VALIDATION")
    print("=" * 70)

    try:
        test_should_take_action()
        test_position_size_multiplier()
        test_estimate_recovery_time()
        test_validate_state()
        test_get_state_summary()
        test_step_batch()
        test_performance_tracking()

        print("\n" + "=" * 70)
        print("✅ ALL UTILITY TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)
        print("\nValidated utilities:")
        print("  1. ✓ should_take_action() - Risk-adjusted trading decisions")
        print("  2. ✓ get_position_size_multiplier() - Dynamic position sizing")
        print("  3. ✓ estimate_recovery_time() - Recovery planning")
        print("  4. ✓ validate_state() - State consistency checking")
        print("  5. ✓ get_state_summary() - Human-readable diagnostics")
        print("  6. ✓ step_batch() - Efficient batch processing")
        print("  7. ✓ Performance tracking - Monitoring and profiling")
        print("=" * 70)
        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
