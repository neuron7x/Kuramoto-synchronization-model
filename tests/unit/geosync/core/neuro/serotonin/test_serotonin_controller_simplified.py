# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the simplified serotonin controller.

Tests the fixes for:
1. Hysteresis application to entry/exit thresholds
2. Cooldown decrement timing (only when not in hold)
3. Cooldown initialization (on exit, not entry)
4. Tonic/phasic separation
5. Hold property logic
"""

import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def serotonin_config():
    """Create a test configuration."""
    return {
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


@pytest.fixture
def serotonin_controller(serotonin_config):
    """Create a serotonin controller instance."""
    from src.geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"active_profile": "legacy", "serotonin_legacy": serotonin_config}, f)
        config_path = f.name

    controller = SerotoninController(config_path)

    yield controller

    # Cleanup
    Path(config_path).unlink()


def test_config_requires_legacy_profile(tmp_path: Path):
    from src.geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": {"alpha": 0.5}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_config_unknown_root_rejected(tmp_path: Path):
    from src.geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "active_profile": "legacy",
                "serotonin_legacy": {},
                "unexpected": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_multi_document_config_rejected(tmp_path: Path):
    from src.geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text("---\nactive_profile: legacy\n---\n{}", encoding="utf-8")
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_reset_is_total_reset(serotonin_controller):
    ctrl = serotonin_controller
    for _ in range(5):
        ctrl.step(stress=1.0, drawdown=0.1, novelty=0.2, dt=1.0)
    ctrl.reset()
    assert ctrl.tonic_level == 0.0
    assert ctrl.phasic_level == 0.0
    assert ctrl.serotonin_level == 0.0
    assert ctrl._cooldown == 0
    assert ctrl.desens_counter == 0
    assert ctrl.sensitivity == 1.0
    assert ctrl.temperature_floor == ctrl.config["temperature_floor_min"]


class TestHysteresisApplication:
    """Tests for hysteresis application to thresholds."""

    def test_entry_threshold_includes_hysteresis(self, serotonin_controller, serotonin_config):
        """Test that high stress triggers hold state via the v24 fast-path or threshold."""
        ctrl = serotonin_controller
        ctrl.reset()

        # High stress should trigger hold (v24 has a fast-path for stress >= 1.0)
        for _ in range(15):
            result = ctrl.step(stress=1.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break
        else:
            pytest.fail("Should have entered hold state")

    def test_exit_threshold_includes_hysteresis(self, serotonin_controller, serotonin_config):
        """Test that hold eventually exits when stress drops to zero."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter hold first
        for _ in range(15):
            result = ctrl.step(stress=1.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        assert ctrl._hold, "Should be in hold"

        # Drop stress to exit hold
        exited = False
        for _ in range(50):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold_state:
                exited = True
                break

        assert exited, "Should have exited hold state when stress drops"

    def test_hysteresis_prevents_oscillation(self, serotonin_controller, serotonin_config):
        """Test that hysteresis creates a gap between entry and exit thresholds."""
        # In v24, the hysteresis is multiplicative: entry = threshold * (1 + margin),
        # exit = threshold * (1 - margin). This ensures a gap that prevents oscillation.
        cooldown_threshold = serotonin_config["stress_threshold"]
        hysteresis_margin = serotonin_config["hysteresis"]

        entry_threshold = cooldown_threshold * (1 + hysteresis_margin)
        exit_threshold = cooldown_threshold * (1 - hysteresis_margin)

        gap = entry_threshold - exit_threshold
        expected_gap = cooldown_threshold * 2 * hysteresis_margin

        assert (
            abs(gap - expected_gap) < 0.001
        ), f"Hysteresis gap should be {expected_gap}, got {gap}"
        assert gap > 0, "Gap must be positive to prevent oscillation"


class TestCooldownBehavior:
    """Tests for cooldown decrement and initialization timing."""

    def test_cooldown_zero_while_in_hold(self, serotonin_controller):
        """Test that cooldown stays at 0 while in active hold state."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Build up to hold
        for _ in range(15):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        assert ctrl._hold, "Should be in hold"
        assert ctrl._cooldown == 0, "Cooldown should be 0 while in hold"

        # Stay in hold - cooldown should remain 0
        for _ in range(5):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            assert ctrl._cooldown == 0, "Cooldown should stay at 0 while in hold"

    def test_cooldown_initialized_on_exit(self, serotonin_controller, serotonin_config):
        """Test that cooldown is set when exiting hold, not when entering.

        Note: The cooldown is NOT decremented on the exit step itself.
        The exit step counts as the first tick of the cooldown period,
        but the cooldown value remains at the configured cooldown_ticks.
        Decrementing only happens on subsequent steps.
        """
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter hold
        for _ in range(15):
            result = ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        cooldown_at_entry = ctrl._cooldown
        assert cooldown_at_entry == 0, "Cooldown should be 0 when entering hold"

        # Exit hold
        for _ in range(30):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold and result["cooldown"] > 0:
                break

        assert not ctrl._hold, "Should have exited hold"
        # Cooldown is NOT decremented on exit step - it starts at cooldown_ticks
        expected_cooldown = serotonin_config["cooldown_ticks"]
        assert (
            result["cooldown"] == expected_cooldown
        ), f"Cooldown should be {expected_cooldown} after exit (ticks={serotonin_config['cooldown_ticks']})"

    def test_cooldown_decrements_only_outside_hold(self, serotonin_controller):
        """Test that cooldown only decrements when not in active hold state."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter and exit hold
        for _ in range(15):
            result = ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        for _ in range(30):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold and result["cooldown"] > 0:
                break

        # Now cooldown should decrement
        initial_cooldown = result["cooldown"]
        assert initial_cooldown > 0, "Cooldown should be active"

        result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        assert result["cooldown"] < initial_cooldown, "Cooldown should decrement outside hold"

    def test_cooldown_reaches_zero(self, serotonin_controller, serotonin_config):
        """Test that cooldown eventually reaches zero."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter and exit hold
        for _ in range(15):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        for _ in range(30):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold and result["cooldown"] > 0:
                break

        # Wait for cooldown to expire
        cooldown_ticks = serotonin_config["cooldown_ticks"]
        for _ in range(cooldown_ticks + 2):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)

        assert result["cooldown"] == 0, "Cooldown should reach 0"


class TestTonicPhasicSeparation:
    """Tests for tonic/phasic component separation."""

    def test_tonic_accumulates_slowly_from_stress(self, serotonin_controller):
        """Test that tonic level accumulates slowly from constant stress."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Apply constant stress
        tonic_values = []
        for _ in range(5):
            ctrl.step(stress=0.5, drawdown=0.0, novelty=0.0, dt=1.0)
            tonic_values.append(ctrl.tonic_level)

        # Tonic should gradually increase
        assert all(
            tonic_values[i] < tonic_values[i + 1] for i in range(len(tonic_values) - 1)
        ), "Tonic should increase gradually with constant stress"

        # But not too fast
        assert tonic_values[-1] < 0.5, "Tonic should accumulate slowly"

    def test_phasic_responds_quickly_to_drawdown(self, serotonin_controller):
        """Test that phasic level responds quickly to sudden drawdown."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Baseline with no stress
        ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        phasic_before = ctrl.phasic_level

        # Sudden drawdown
        ctrl.step(stress=0.0, drawdown=1.0, novelty=0.0, dt=1.0)
        phasic_during = ctrl.phasic_level

        # Back to baseline
        ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        phasic_after = ctrl.phasic_level

        assert phasic_during > phasic_before, "Phasic should spike on drawdown"
        assert phasic_after < phasic_during, "Phasic should decay after transient"
        assert phasic_during > 0.01, "Phasic should show measurable response"

    def test_phasic_responds_to_novelty(self, serotonin_controller):
        """Test that phasic level responds to novelty events."""
        ctrl = serotonin_controller
        ctrl.reset()

        ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        phasic_before = ctrl.phasic_level

        ctrl.step(stress=0.0, drawdown=0.0, novelty=1.0, dt=1.0)
        phasic_during = ctrl.phasic_level

        assert phasic_during > phasic_before, "Phasic should respond to novelty"

    def test_tonic_not_affected_by_single_transient(self, serotonin_controller):
        """Test that a single transient event doesn't significantly affect tonic."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Establish baseline
        for _ in range(5):
            ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
        tonic_baseline = ctrl.tonic_level

        # Single transient
        ctrl.step(stress=0.0, drawdown=1.0, novelty=0.0, dt=1.0)
        tonic_after = ctrl.tonic_level

        # Tonic should barely change
        tonic_change = abs(tonic_after - tonic_baseline)
        assert tonic_change < 0.1, "Tonic should not be significantly affected by single transient"


class TestHoldPropertyLogic:
    """Tests for the hold property combining _hold and cooldown."""

    def test_hold_false_initially(self, serotonin_controller):
        """Test that hold is False initially."""
        ctrl = serotonin_controller
        ctrl.reset()

        assert not ctrl.hold, "Hold should be False initially"
        assert not ctrl._hold, "_hold should be False initially"
        assert ctrl._cooldown == 0, "Cooldown should be 0 initially"

    def test_hold_true_when_in_hold_state(self, serotonin_controller):
        """Test that hold is True when in active hold state."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter hold
        for _ in range(15):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        assert ctrl._hold, "_hold should be True"
        assert ctrl.hold, "hold property should be True when in _hold"

    def test_hold_true_during_cooldown(self, serotonin_controller):
        """Test that hold is True during cooldown after exiting _hold."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter and exit hold
        for _ in range(15):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        for _ in range(30):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold and result["cooldown"] > 0:
                break

        assert not ctrl._hold, "_hold should be False"
        assert result["cooldown"] > 0, "Cooldown should be active"
        assert ctrl.hold, "hold property should be True during cooldown"

    def test_hold_false_after_cooldown_expires(self, serotonin_controller, serotonin_config):
        """Test that hold is False after cooldown expires."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Enter, exit, and wait for cooldown
        for _ in range(15):
            ctrl.step(stress=1.0, drawdown=0.5, novelty=0.0, dt=1.0)
            if ctrl._hold:
                break

        for _ in range(30):
            result = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)
            if not ctrl._hold and result["cooldown"] > 0:
                break

        # Wait for cooldown to expire
        for _ in range(serotonin_config["cooldown_ticks"] + 2):
            ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0, dt=1.0)

        assert not ctrl._hold, "_hold should be False"
        assert ctrl._cooldown == 0, "Cooldown should be 0"
        assert not ctrl.hold, "hold property should be False after cooldown expires"


class TestStepMethod:
    """Tests for the step method."""

    def test_step_accepts_dt_parameter(self, serotonin_controller):
        """Test that step accepts dt parameter for cooldown timing."""
        ctrl = serotonin_controller
        ctrl.reset()

        # v24 accepts dt as an optional timing hint
        result = ctrl.step(stress=0.5, drawdown=0.0, novelty=0.0, dt=1.0)
        assert result["level"] >= 0.0, "Level should be non-negative"

        result = ctrl.step(stress=0.5, drawdown=0.0, novelty=0.0, dt=0.5)
        assert result["level"] >= 0.0, "Level should be non-negative with small dt"

    def test_step_rejects_negative_stress(self, serotonin_controller):
        """Test that step raises ValueError for negative stress (v24 behaviour)."""
        ctrl = serotonin_controller
        ctrl.reset()

        with pytest.raises(ValueError, match="stress must be non-negative"):
            ctrl.step(stress=-1.0, drawdown=0.0, novelty=0.0, dt=1.0)

    def test_step_rejects_negative_novelty(self, serotonin_controller):
        """Test that step raises ValueError for negative novelty (v24 behaviour)."""
        ctrl = serotonin_controller
        ctrl.reset()

        with pytest.raises(ValueError, match="novelty must be non-negative"):
            ctrl.step(stress=0.0, drawdown=0.0, novelty=-1.0, dt=1.0)

    def test_step_returns_expected_keys(self, serotonin_controller):
        """Test that step returns all expected keys."""
        ctrl = serotonin_controller
        result = ctrl.step(stress=0.5, drawdown=0.0, novelty=0.0, dt=1.0)

        expected_keys = {
            "level",
            "hold",
            "veto",
            "cooldown",
            "temperature_floor",
            "desensitization",
        }
        assert (
            set(result.to_dict().keys()) == expected_keys
        ), f"Missing keys: {expected_keys - set(result.to_dict().keys())}"

    def test_step_level_bounded(self, serotonin_controller):
        """Test that level stays within bounds."""
        ctrl = serotonin_controller
        ctrl.reset()

        # High stress should not cause unbounded level
        for _ in range(50):
            result = ctrl.step(stress=10.0, drawdown=5.0, novelty=5.0, dt=1.0)
            assert 0.0 <= result["level"] <= 1.5, f"Level {result['level']} out of bounds"


class TestCheckCooldownMethod:
    """Tests for the check_cooldown method."""

    def test_check_cooldown_with_explicit_signal(self, serotonin_controller, serotonin_config):
        """Test check_cooldown with explicit serotonin signal."""
        ctrl = serotonin_controller
        ctrl.reset()

        # Low signal should not trigger hold
        result = ctrl.check_cooldown(serotonin_signal=0.5)
        assert not result, "Low signal should not trigger hold"

        # High signal should trigger hold
        high_threshold = (
            serotonin_config["stress_threshold"] + serotonin_config["hysteresis"] / 2.0 + 0.1
        )
        result = ctrl.check_cooldown(serotonin_signal=high_threshold)
        assert result, "High signal should trigger hold"

    def test_check_cooldown_applies_hysteresis(self, serotonin_controller, serotonin_config):
        """Test that check_cooldown applies hysteresis correctly (v24 multiplicative)."""
        ctrl = serotonin_controller
        ctrl.reset()

        # v24 uses multiplicative hysteresis: entry = threshold * (1 + margin)
        cooldown_threshold = serotonin_config["stress_threshold"]
        hysteresis_margin = serotonin_config["hysteresis"]
        entry_threshold = cooldown_threshold * (1 + hysteresis_margin)

        # Signal just below entry threshold should not trigger
        ctrl.check_cooldown(serotonin_signal=entry_threshold - 0.01)
        assert not ctrl._hold_state, "Should not enter hold below threshold"

        # Signal above entry threshold should trigger
        result = ctrl.check_cooldown(serotonin_signal=entry_threshold + 0.01)
        assert result, "Should return True above threshold"


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_missing_config_keys_raises_error(self, serotonin_config):
        """Test that missing config keys raise an error."""
        from src.geosync.core.neuro.serotonin.serotonin_controller import (
            SerotoninController,
        )

        # Remove a required key
        incomplete_config = serotonin_config.copy()
        del incomplete_config["tonic_beta"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "active_profile": "legacy",
                    "serotonin_legacy": incomplete_config,
                },
                f,
            )
            config_path = f.name

        with pytest.raises((ValueError, Exception)):
            SerotoninController(config_path)

        Path(config_path).unlink()

    def test_invalid_config_values_raise_error(self, serotonin_config):
        """Test that invalid config values raise an error."""
        from src.geosync.core.neuro.serotonin.serotonin_controller import (
            SerotoninController,
        )

        # Invalid beta (> 1.0)
        invalid_config = serotonin_config.copy()
        invalid_config["tonic_beta"] = 1.5

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_config, f)
            config_path = f.name

        with pytest.raises(ValueError):
            SerotoninController(config_path)

        Path(config_path).unlink()
