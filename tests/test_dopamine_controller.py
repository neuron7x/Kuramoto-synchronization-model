# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for DopamineController neuromodulator system.

This module validates the dopamine-based reinforcement learning controller
that modulates trading agent behavior through reward prediction errors and
appetitive state estimation.

Test Coverage:
- Configuration validation: required keys and parameter ranges
- Appetitive state estimation: reward, novelty, motivation, and value integration
- RPE computation: reward prediction error calculations
- Dopamine signal computation: phasic and tonic levels
- Temperature scheduling: exploration vs exploitation balance
- Action value modulation: Q-value adjustment via dopamine
- Go/No-Go thresholds: invigoration and suppression gates
- Meta-adaptation: online parameter tuning based on performance metrics
- State management: reset, dump, and load operations
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import pytest
import yaml

from geosync.core.neuro.dopamine.dopamine_controller import DopamineController


@pytest.fixture(autouse=True)
def _seed_rng() -> None:
    random.seed(0)


@pytest.fixture
def config_dict() -> Dict[str, object]:
    return {
        "version": "2.2.0",
        "discount_gamma": 0.98,
        "learning_rate_v": 0.1,
        "decay_rate": 0.05,
        "burst_factor": 2.5,
        "k": 1.0,
        "theta": 0.5,
        "w_r": 0.60,
        "w_n": 0.20,
        "w_m": 0.15,
        "w_v": 0.20,
        "novelty_mode": "abs_rpe",
        "c_absrpe": 0.10,
        "baseline": 0.5,
        "delta_gain": 0.5,
        "base_temperature": 1.0,
        "min_temperature": 0.05,
        "temp_k": 1.2,
        "neg_rpe_temp_gain": 0.5,
        "max_temp_multiplier": 3.0,
        "invigoration_threshold": 0.75,
        "no_go_threshold": 0.25,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "meta_cooldown_ticks": 2,
        "metric_interval": 1,
        "meta_adapt_rules": {
            "good": {
                "learning_rate_v": 1.01,
                "delta_gain": 1.01,
                "base_temperature": 0.99,
            },
            "bad": {
                "learning_rate_v": 0.99,
                "delta_gain": 0.99,
                "base_temperature": 1.01,
            },
            "neutral": {
                "learning_rate_v": 1.0,
                "delta_gain": 1.0,
                "base_temperature": 1.0,
            },
        },
    }


@pytest.fixture
def controller(tmp_path, config_dict: Dict[str, object]) -> DopamineController:
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    telemetry: List[Tuple[str, float]] = []

    def stub_logger(name: str, value: float) -> None:
        telemetry.append((name, float(value)))

    ctrl = DopamineController(str(cfg_path), logger=stub_logger)
    ctrl._telemetry = telemetry  # type: ignore[attr-defined]
    return ctrl


def test_configuration_validation_missing_key(tmp_path) -> None:
    """Test that DopamineController rejects incomplete configuration.

    The controller requires all mandatory configuration keys to be present.
    Missing keys should raise ValueError with a descriptive error message.
    """
    cfg = {"discount_gamma": 0.9}
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    with pytest.raises(ValueError, match=".+"):
        DopamineController(str(cfg_path))


def test_configuration_validation_ranges(tmp_path, config_dict: Dict[str, object]) -> None:
    """Test that DopamineController validates parameter ranges.

    Parameters must be within valid ranges (e.g., delta_gain must be <= 1.0).
    Out-of-range values should raise ValueError.
    """
    config_dict["delta_gain"] = 1.5
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)
    with pytest.raises(ValueError, match=".+"):
        DopamineController(str(cfg_path))


def test_estimate_appetitive_state_with_abs_rpe(controller: DopamineController) -> None:
    """Test appetitive state estimation with absolute RPE novelty mode.

    The appetitive state combines reward, novelty (based on abs RPE),
    motivation, and value with configured weights. This test validates
    the weighted sum computation.

    Validates:
    - Novelty is computed from absolute RPE
    - All four components are correctly weighted
    - Final appetitive state matches expected value
    """
    controller.last_rpe = 0.4
    appetitive = controller.estimate_appetitive_state(1.0, 0.5, 0.2, 0.3)
    cfg = controller.config
    novelty_eff = 0.5 + cfg["c_absrpe"] * abs(0.4)
    expected = cfg["w_r"] * 1.0 + cfg["w_n"] * novelty_eff + cfg["w_m"] * 0.2 + cfg["w_v"] * 0.3
    assert appetitive == pytest.approx(
        expected, rel=1e-6
    ), f"Appetitive state mismatch: expected {expected}, got {appetitive}"


def test_appetitive_state_rejects_negative(controller: DopamineController) -> None:
    """Test that negative reward values are rejected.

    The appetitive state estimation should validate that reward is non-negative,
    as negative rewards indicate an error in the reward computation logic.
    """
    with pytest.raises(ValueError, match=".+"):
        controller.estimate_appetitive_state(-0.1, 0.0, 0.0, 0.0)


def test_compute_rpe_sign_and_magnitude(controller: DopamineController) -> None:
    """Test reward prediction error (RPE) computation and value update.

    RPE = reward + gamma * next_value - value
    The value estimate should be updated via: value += learning_rate * RPE

    Validates:
    - RPE has correct sign and magnitude
    - Value estimate is updated correctly
    - TD learning rule is applied properly
    """
    reward, value, next_value = 0.1, 0.2, 0.5
    rpe = controller.compute_rpe(reward, value, next_value)
    assert math.copysign(1.0, rpe) == math.copysign(
        1.0, 0.39
    ), f"RPE sign mismatch: expected positive, got {rpe}"
    assert rpe == pytest.approx(0.39, rel=1e-6), f"RPE magnitude mismatch: expected 0.39, got {rpe}"
    updated_value = controller.update_value_estimate()
    expected_update = 0.0 + 0.1 * 0.39
    assert updated_value == pytest.approx(
        expected_update, rel=1e-6
    ), f"Value update mismatch: expected {expected_update}, got {updated_value}"


def test_dopamine_signal_clamped_and_stable(controller: DopamineController) -> None:
    """Test that dopamine signal is clamped to [0, 1] range.

    Even with extreme RPE values, the dopamine signal should remain bounded
    to prevent numerical instability in downstream computations.

    Validates:
    - High RPE values produce clamped dopamine signal
    - Low RPE values produce clamped dopamine signal
    - Signal never exceeds [0, 1] bounds
    """
    controller.compute_rpe(1e6, 0.0, 0.0)
    high = controller.compute_dopamine_signal(5.0, controller.last_rpe)
    assert 0.0 <= high <= 1.0, f"Dopamine signal should be in [0,1], got {high} for high RPE"
    controller.compute_rpe(-1e6, 0.0, 0.0)
    low = controller.compute_dopamine_signal(0.0, controller.last_rpe)
    assert 0.0 <= low <= 1.0, f"Dopamine signal should be in [0,1], got {low} for low RPE"


def test_temperature_monotonic_decrease(controller: DopamineController) -> None:
    """Test that temperature decreases monotonically with dopamine signal.

    Higher dopamine signals (indicating better outcomes) should reduce
    exploration temperature, favoring exploitation of known good actions.

    Validates:
    - Temperature decreases as dopamine increases
    - Monotonic relationship is maintained
    - Annealing schedule works as expected
    """
    readings = []
    for appetitive, rpe in ((0.1, 0.0), (0.5, 0.2), (1.0, 0.8)):
        controller.compute_rpe(rpe, 0.0, 0.0)
        da = controller.compute_dopamine_signal(appetitive, rpe)
        readings.append(controller.compute_temperature(da))
    assert (
        readings[0] >= readings[1] >= readings[2]
    ), f"Temperature should decrease monotonically, got {readings}"


def test_negative_rpe_increases_temperature(controller: DopamineController) -> None:
    """Test that negative RPE increases exploration temperature.

    When outcomes are worse than expected (negative RPE), the system should
    increase exploration to find better alternatives.

    Validates:
    - Negative RPE triggers temperature increase
    - Temperature adjustment is applied correctly
    - Exploration is promoted after disappointing outcomes
    """
    controller.compute_rpe(0.0, 0.0, 0.0)
    da = controller.compute_dopamine_signal(0.5, 0.0)
    base_temp = controller.compute_temperature(da)
    controller.last_rpe = -0.8
    hotter = controller.compute_temperature(da)
    assert (
        hotter >= base_temp
    ), f"Negative RPE should increase temperature: base={base_temp}, after={hotter}"


def test_modulate_action_value(controller: DopamineController) -> None:
    """Test action value modulation via dopamine signal.

    Dopamine modulates Q-values: Q_mod = Q * (1 + delta_gain * (DA - baseline))
    High dopamine boosts action values (invigoration), low dopamine reduces them.

    Validates:
    - Modulation formula is applied correctly
    - High dopamine amplifies action values
    - Baseline dopamine level has no effect
    """
    q_mod = controller.modulate_action_value(2.0, dopamine_signal=0.8)
    cfg = controller.config
    expected = 2.0 * (1.0 + cfg["delta_gain"] * (0.8 - cfg["baseline"]))
    assert q_mod == pytest.approx(
        expected, rel=1e-6
    ), f"Modulated Q-value mismatch: expected {expected}, got {q_mod}"


def test_go_no_go_thresholds(controller: DopamineController) -> None:
    """Test invigoration and suppression threshold gates.

    Dopamine above invigoration threshold promotes action initiation (go).
    Dopamine below suppression threshold inhibits actions (no-go).

    Validates:
    - Invigoration threshold correctly identifies high dopamine states
    - Suppression threshold correctly identifies low dopamine states
    - Thresholds work independently
    """
    assert (
        controller.check_invigoration(0.8) is True
    ), "Dopamine 0.8 should exceed invigoration threshold"
    assert (
        controller.check_invigoration(0.6) is False
    ), "Dopamine 0.6 should not exceed invigoration threshold"
    assert (
        controller.check_suppress(0.2) is True
    ), "Dopamine 0.2 should be below suppression threshold"
    assert (
        controller.check_suppress(0.4) is False
    ), "Dopamine 0.4 should not be below suppression threshold"


def test_meta_adapt_respects_cooldown(controller: DopamineController) -> None:
    """Test that meta-adaptation respects cooldown period.

    Meta-adaptation adjusts controller parameters based on performance metrics.
    Cooldown prevents rapid oscillations from consecutive adaptations.

    Validates:
    - Good performance increases learning rate
    - Cooldown prevents immediate re-adaptation
    - After cooldown expires, bad performance decreases learning rate
    """
    cfg_snapshot = {
        "learning_rate_v": controller.config["learning_rate_v"],
        "delta_gain": controller.config["delta_gain"],
        "base_temperature": controller.config["base_temperature"],
    }
    controller.meta_adapt({"drawdown": -0.03, "sharpe": 1.2})
    assert (
        controller.config["learning_rate_v"] > cfg_snapshot["learning_rate_v"]
    ), "Good performance should increase learning rate"
    # During cooldown, bad performance should not change parameters
    controller.meta_adapt({"drawdown": -0.10, "sharpe": 0.2})
    assert (
        controller.config["learning_rate_v"] > cfg_snapshot["learning_rate_v"]
    ), "Parameters should not change during cooldown"
    # After cooldown, bad performance should decrease learning rate
    controller._meta_cooldown_counter = 0
    controller.meta_adapt({"drawdown": -0.10, "sharpe": 0.2})
    assert (
        controller.config["learning_rate_v"] < cfg_snapshot["learning_rate_v"]
    ), "Bad performance after cooldown should decrease learning rate"


def test_reset_and_state_roundtrip(controller: DopamineController) -> None:
    """Test state persistence: dump, reset, and load operations.

    The controller should support saving internal state, resetting to defaults,
    and restoring saved state for checkpointing and recovery.

    Validates:
    - State can be dumped after operations
    - Reset clears all internal state
    - Loaded state matches previously dumped state
    - Round-trip preservation of all state variables
    """
    controller.compute_rpe(0.2, 0.1, 0.3)
    controller.update_value_estimate()
    controller.compute_dopamine_signal(0.9, 0.4)
    state = controller.dump_state()
    controller.reset_state()
    reset_state = controller.dump_state()
    expected_reset = {
        "tonic_level": 0.0,
        "phasic_level": 0.0,
        "dopamine_level": 0.0,
        "value_estimate": 0.0,
        "last_rpe": 0.0,
        "adaptive_base_temperature": 1.0,
        "rpe_mean": 0.0,
        "rpe_sq_mean": 0.0,
        "temp_adam_m": 0.0,
        "temp_adam_v": 0.0,
        "temp_adam_t": 0.0,
        "release_gate_open": 1.0,
        "last_temperature": 1.0,
    }
    assert (
        reset_state == expected_reset
    ), f"Reset state should be zero: expected {expected_reset}, got {reset_state}"
    controller.load_state(state)
    loaded_state = controller.dump_state()
    assert loaded_state == state, f"State round-trip failed: expected {state}, got {loaded_state}"


def test_load_state_validation(controller: DopamineController) -> None:
    with pytest.raises(ValueError):
        controller.load_state({"tonic_level": 0.0})


def test_save_and_to_dict(controller: DopamineController, tmp_path) -> None:
    controller.compute_rpe(0.2, 0.1, 0.3)
    controller.update_value_estimate()
    controller.compute_dopamine_signal(0.9, 0.4)

    out_path = tmp_path / "out_dopamine.yaml"
    controller.save_config_to_yaml(str(out_path))
    assert out_path.exists()

    with open(out_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["version"] == "2.2.0"
    assert set(cfg["meta_adapt_rules"].keys()) == {"good", "bad", "neutral"}

    snapshot = controller.to_dict()
    assert snapshot["version"] == "2.2.0"
    for key in (
        "tonic_level",
        "phasic_level",
        "dopamine_level",
        "value_estimate",
        "last_rpe",
    ):
        assert key in snapshot


def test_update_metrics_respects_interval(controller: DopamineController) -> None:
    controller.config["metric_interval"] = 2
    controller._metric_interval = 2
    telemetry: List[Tuple[str, float]] = controller._telemetry  # type: ignore[attr-defined]
    controller.update_metrics()
    first_len = len(telemetry)
    controller.update_metrics()
    assert len(telemetry) > first_len


def test_unknown_config_key_rejected(tmp_path, config_dict: Dict[str, object]) -> None:
    config_dict["unexpected"] = 1
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)
    with pytest.raises(ValueError):
        DopamineController(str(cfg_path))


def test_discount_gamma_override_validated(controller: DopamineController) -> None:
    controller.compute_rpe(0.1, 0.2, 0.3, discount_gamma=0.5)
    with pytest.raises(ValueError):
        controller.compute_rpe(0.1, 0.2, 0.3, discount_gamma=1.5)
