from __future__ import annotations

import importlib.util
import json
import logging
import math
import sys
from pathlib import Path
from time import perf_counter, time
from typing import Mapping

import numpy as np
import pytest
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Direct import to avoid dependency issues in tests
spec = importlib.util.spec_from_file_location(
    "serotonin_controller",
    Path(__file__).parent.parent / "serotonin" / "serotonin_controller.py",
)
serotonin_module = importlib.util.module_from_spec(spec)
sys.modules["serotonin_controller"] = serotonin_module
spec.loader.exec_module(serotonin_module)

SerotoninController = serotonin_module.SerotoninController
SerotoninConfig = serotonin_module.SerotoninConfig
_generate_config_table = serotonin_module._generate_config_table

pytestmark = pytest.mark.L1


@pytest.fixture
def config_dict():
    return {
        "alpha": 0.42,
        "beta": 0.28,
        "gamma": 0.32,
        "delta_rho": 0.18,
        "k": 1.0,
        "theta": 0.5,
        "delta": 0.8,
        "za_bias": -0.33,
        "decay_rate": 0.05,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 100,
        "desens_rate": 0.01,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "beta_temper": 0.12,
        "max_desens_counter": 1000,
        "phase_threshold": 0.4,
        "burst_factor": 2.5,
        "mod_t_max": 4.0,
        "mod_t_half": 24.0,
        "mod_k": 0.7,
        "tick_hours": 1.0,
        "phase_kappa": 0.08,
        "desens_gain": 0.12,
        "gate_veto": 0.9,
        "phasic_veto": 1.0,
        "temperature_floor_min": 0.05,
        "temperature_floor_max": 0.4,
    }


@pytest.fixture
def controller(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"active_profile": "v24", "serotonin_v24": config_dict},
            f,
        )

    def stub_logger(name: str, value: float) -> None:
        logging.getLogger(__name__).info("%s: %s", name, value)

    return SerotoninController(str(cfg_path), logger=stub_logger)


def test_aversive_state(controller):
    s = controller.estimate_aversive_state(
        market_vol=1.0,
        free_energy=0.5,
        cum_losses=0.2,
        rho_loss=-0.90,
    )
    # v2.4.0 uses non-linear transforms:
    # - sqrt for market_vol (Weber-Fechner)
    # - quadratic for cum_losses (pain amplification)
    # - tanh saturation
    vol_contribution = 0.42 * math.sqrt(1.0)
    fe_contribution = 0.28 * 0.5
    loss_contribution = 0.32 * (0.2 + 0.5 * 0.2**2)
    rho_contribution = 0.18 * (1 - (-0.90))
    release = vol_contribution + fe_contribution + loss_contribution + rho_contribution
    expected = 3.0 * math.tanh(release / 3.0)
    assert s == pytest.approx(expected, rel=1e-3)


def test_aversive_state_validation(controller):
    with pytest.raises(ValueError):
        controller.estimate_aversive_state(-1.0, 0.5, 0.2, -0.90)


def test_serotonin_signal_updates_tonic_and_sensitivity(controller):
    ser1 = controller.compute_serotonin_signal(1.0)
    tonic1 = controller.tonic_level
    assert tonic1 > 0.05

    ser2 = controller.compute_serotonin_signal(1.0)
    tonic2 = controller.tonic_level
    assert tonic2 > tonic1

    assert 0.0 <= ser1 <= 1.0
    assert 0.0 <= ser2 <= 1.0
    assert controller.serotonin_level == pytest.approx(ser2, rel=1e-6)


def test_temperature_floor_tracks_serotonin(controller):
    cfg = controller.config
    floor_min = cfg["temperature_floor_min"]
    floor_max = cfg["temperature_floor_max"]
    first = controller.temperature_floor
    assert floor_min <= first <= floor_max
    controller.compute_serotonin_signal(0.5)
    mid = controller.temperature_floor
    controller.compute_serotonin_signal(2.0)
    high = controller.temperature_floor
    assert floor_min <= mid <= floor_max
    assert floor_min <= high <= floor_max
    assert mid >= first
    assert high >= mid


def test_serotonin_signal_validation(controller):
    with pytest.raises(ValueError):
        controller.compute_serotonin_signal(-1.0)


def test_desensitization_and_recovery(controller):
    for _ in range(150):
        controller.compute_serotonin_signal(2.0)
    assert controller.sensitivity < 1.0

    sens_before = controller.sensitivity
    for _ in range(50):
        controller.compute_serotonin_signal(0.1)
    assert controller.sensitivity > sens_before
    assert controller.sensitivity <= 1.0


def test_desens_counter_cap(controller):
    for _ in range(2000):
        controller.compute_serotonin_signal(2.0)
    assert controller.desens_counter == 1000


def test_desens_gain_controls_floor(controller):
    controller.config["desens_gain"] = 2.0
    for _ in range(150):
        controller.compute_serotonin_signal(5.0)
    assert controller.sensitivity == pytest.approx(0.1, rel=1e-6)


def test_modulate_action_prob(controller):
    ser = 0.6
    prob = controller.modulate_action_prob(
        original_prob=0.9,
        serotonin_signal=ser,
        za_bias=-0.33,
    )
    # v2.4.0 uses quadratic inhibition for progressive effect
    inhibition_strength = ser**2
    inhibition_factor = 1.0 - inhibition_strength * 0.8
    inhibited = 0.9 * max(0.0, inhibition_factor)
    # Negative bias with sigmoid-like application
    bias_factor = 1.0 + (-0.33) * (1.0 - math.exp(-2.0 * ser))
    expected = float(np.clip(inhibited * bias_factor, 0.0, 1.0))
    assert prob == pytest.approx(expected, rel=1e-3)


def test_modulate_action_prob_validation(controller):
    with pytest.raises(ValueError):
        controller.modulate_action_prob(-0.1)


def test_apply_internal_shift(controller):
    ser = controller.compute_serotonin_signal(1.5)
    grad = 2.0
    shifted = controller.apply_internal_shift(
        exploitation_gradient=grad,
        serotonin_signal=ser,
        beta_temper=0.12,
    )
    # v2.4.0 uses power-law tempering (power 1.5) for smoother transitions
    tempering_curve = ser**1.5
    tempering_factor = 1.0 - 0.12 * tempering_curve
    expected = grad * max(0.0, tempering_factor)
    assert shifted == pytest.approx(expected, rel=1e-3)


def test_apply_internal_shift_validation(controller):
    with pytest.raises(ValueError):
        controller.apply_internal_shift(-1.0)


def test_check_cooldown(controller):
    controller.phasic_level = 1.2
    controller.gate_level = 0.95
    assert controller.check_cooldown(0.6) is True
    controller.phasic_level = 0.5
    controller.gate_level = 0.5
    assert controller.check_cooldown(0.6) is False


def test_gate_veto_configurable(controller):
    controller.config["gate_veto"] = 0.5
    controller.gate_level = 0.6
    assert controller.check_cooldown(0.3) is True


def test_meta_adapt_increases_weights_on_deep_drawdown(controller):
    cfg_before = controller.config.copy()
    controller.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
    c = math.exp(-controller.config["tick_hours"] / controller.config["mod_t_half"]) * (
        1 - math.exp(-controller.config["tick_hours"] / controller.config["mod_t_max"])
    )
    modulation = 1 + controller.config["mod_k"] * c
    assert controller.config["alpha"] == pytest.approx(
        cfg_before["alpha"] * 1.01 * modulation, rel=1e-3
    )
    assert controller.config["gamma"] == pytest.approx(
        cfg_before["gamma"] * 1.01 * modulation, rel=1e-3
    )


def test_meta_adapt_guard_reverts(controller):
    controller.set_tacl_guard(lambda name, payload: False)
    cfg_before = controller.config.copy()
    controller.meta_adapt({"drawdown": -0.1, "sharpe": 0.5})
    assert controller.config == cfg_before


def test_meta_adapt_guard_payload(controller):
    captured = {}

    def guard(name: str, payload: Mapping[str, float]) -> bool:
        captured["name"] = name
        captured["payload"] = dict(payload)
        return True

    controller.set_tacl_guard(guard)
    controller.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
    assert captured["name"] == "serotonin_meta_adapt"
    assert "modulation" in captured["payload"]


def test_update_metrics(caplog, controller):
    caplog.set_level(logging.INFO)
    controller.update_metrics()
    assert "serotonin_level" in caplog.text
    assert "serotonin_tonic_level" in caplog.text
    assert "serotonin_sensitivity" in caplog.text
    assert "serotonin_phasic_level" in caplog.text
    assert "serotonin_gate_level" in caplog.text
    assert "serotonin_temperature_floor" in caplog.text


def test_save_and_to_dict(controller, tmp_path):
    controller.config["alpha"] *= 1.05
    out_path = tmp_path / "out_serotonin.yaml"
    controller.save_config_to_yaml(str(out_path))
    assert out_path.exists()
    with open(out_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["alpha"] == pytest.approx(controller.config["alpha"], rel=1e-6)
    state = controller.to_dict()
    assert "tonic_level" in state
    assert "sensitivity" in state
    assert "alpha" in state
    assert "phasic_level" in state
    assert "gate_level" in state
    assert "decay_rate" in state
    assert "temperature_floor" in state


def test_audit_file_created(controller, tmp_path):
    out_path = tmp_path / "serotonin.yaml"
    controller.save_config_to_yaml(str(out_path))
    audit_dir = out_path.parent / "audit"
    assert audit_dir.exists()
    audits = list(audit_dir.glob("serotonin_*.yaml"))
    assert audits, "expected audit snapshot"


def test_phase_kappa_required(tmp_path, config_dict):
    cfg = dict(config_dict)
    cfg.pop("phase_kappa")
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": cfg}, f)
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_env_config_dir_fallback(tmp_path, config_dict, monkeypatch):
    env_dir = tmp_path / "envcfg"
    env_dir.mkdir()
    cfg_path = env_dir / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)
    monkeypatch.setenv("TRADEPULSE_CONFIG_DIR", str(env_dir))
    controller = SerotoninController("missing.yaml")
    assert controller.config_path == str(cfg_path)


def test_tick_hours_modulation_effect(tmp_path, config_dict):
    fast_cfg = dict(config_dict)
    slow_cfg = dict(config_dict)
    fast_cfg["tick_hours"] = 0.25
    slow_cfg["tick_hours"] = 4.0
    fast_path = tmp_path / "fast.yaml"
    slow_path = tmp_path / "slow.yaml"
    for path, cfg in ((fast_path, fast_cfg), (slow_path, slow_cfg)):
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"active_profile": "v24", "serotonin_v24": cfg}, f)
    fast = SerotoninController(str(fast_path))
    slow = SerotoninController(str(slow_path))
    fast.meta_adapt({"drawdown": -0.1, "sharpe": 1.5})
    slow.meta_adapt({"drawdown": -0.1, "sharpe": 1.5})
    assert fast.config["alpha"] != slow.config["alpha"]


def test_rho_loss_clamping(controller):
    base = controller.estimate_aversive_state(1.0, 0.5, 0.2, 10.0)
    clamped = controller.estimate_aversive_state(1.0, 0.5, 0.2, 1.0)
    assert base == clamped
    neg = controller.estimate_aversive_state(1.0, 0.5, 0.2, -10.0)
    lower = controller.estimate_aversive_state(1.0, 0.5, 0.2, -1.0)
    assert neg == lower


def test_serotonin_monotonicity(controller):
    responses = [
        controller.compute_serotonin_signal(val) for val in np.linspace(0, 3, 15)
    ]
    assert responses == sorted(responses)
    assert all(0.0 <= r <= 1.0 for r in responses)


def test_config_schema_and_table(controller):
    schema = controller.config_schema()
    assert "properties" in schema
    table = _generate_config_table(schema)
    assert "phase_kappa" in table
    json.dumps(schema)


def test_to_dict_snapshot(controller):
    controller.compute_serotonin_signal(1.2)
    controller.compute_serotonin_signal(0.6)
    snapshot = controller.to_dict()
    assert json.dumps(snapshot, sort_keys=True)
    assert snapshot["gate_level"] == controller.gate_level
    assert snapshot["temperature_floor"] == controller.temperature_floor


def test_compute_serotonin_signal_performance(controller):
    start = perf_counter()
    for _ in range(100_000):
        controller.compute_serotonin_signal(0.8)
    duration = perf_counter() - start
    assert duration < 1.5


def test_missing_probability_raises(controller):
    with pytest.raises(ValueError):
        controller.modulate_action_prob(1.5)


def test_serialisation_after_guard_rejection(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)
    controller = SerotoninController(str(cfg_path))
    controller.set_tacl_guard(lambda name, payload: False)
    controller.meta_adapt({"drawdown": -0.2, "sharpe": 0.5})
    out = controller.to_dict()
    assert out["alpha"] == pytest.approx(config_dict["alpha"], rel=1e-6)


def test_config_table_matches_schema():
    schema = SerotoninConfig.model_json_schema()
    table = _generate_config_table(schema)
    for key in SerotoninConfig.model_json_schema()["properties"].keys():
        assert key in table


def test_tau_to_decay_derivation(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    config_dict["tau_5ht_ms"] = 150.0
    config_dict["step_ms"] = 1000.0
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)

    controller = SerotoninController(str(cfg_path), logger=lambda *_: None)
    expected = 1.0 - math.exp(-1000.0 / 150.0)
    assert controller.config["decay_rate"] == pytest.approx(expected, rel=1e-6)


def test_phase_gate_monotonic_around_threshold(tmp_path, config_dict):
    cfg_path = tmp_path / "s.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)
    below = SerotoninController(str(cfg_path), logger=lambda *_: None)
    above = SerotoninController(str(cfg_path), logger=lambda *_: None)
    below.compute_serotonin_signal(config_dict["phase_threshold"] - 0.05)
    above.compute_serotonin_signal(config_dict["phase_threshold"] + 0.05)
    assert 0.0 <= below.gate_level <= 1.0
    assert 0.0 <= above.gate_level <= 1.0
    assert above.phasic_level > below.phasic_level


def test_meta_adapt_tick_hours_scaling(tmp_path, config_dict):
    slow_cfg = dict(config_dict)
    fast_cfg = dict(config_dict)
    slow_cfg["tick_hours"] = 4.0
    fast_cfg["tick_hours"] = 0.25

    slow_path = tmp_path / "slow.yaml"
    fast_path = tmp_path / "fast.yaml"
    with open(slow_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": slow_cfg}, f)
    with open(fast_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": fast_cfg}, f)

    slow = SerotoninController(str(slow_path), logger=lambda *_: None)
    fast = SerotoninController(str(fast_path), logger=lambda *_: None)

    slow.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
    fast.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})

    slow_c = math.exp(-slow.config["tick_hours"] / slow.config["mod_t_half"]) * (
        1 - math.exp(-slow.config["tick_hours"] / slow.config["mod_t_max"])
    )
    fast_c = math.exp(-fast.config["tick_hours"] / fast.config["mod_t_half"]) * (
        1 - math.exp(-fast.config["tick_hours"] / fast.config["mod_t_max"])
    )
    slow_expected = 1 + slow.config["mod_k"] * slow_c
    fast_expected = 1 + fast.config["mod_k"] * fast_c

    assert slow.config["alpha"] == pytest.approx(0.42 * 1.01 * slow_expected, rel=1e-3)
    assert fast.config["alpha"] == pytest.approx(0.42 * 1.01 * fast_expected, rel=1e-3)
    assert slow.config["alpha"] != pytest.approx(fast.config["alpha"], rel=1e-4)


def test_estimate_aversive_state_clamps_rho_loss(controller):
    over = controller.estimate_aversive_state(1.0, 0.5, 0.2, 5.0)
    under = controller.estimate_aversive_state(1.0, 0.5, 0.2, -5.0)
    base = controller.estimate_aversive_state(1.0, 0.5, 0.2, 1.0)
    assert over == pytest.approx(base, rel=1e-6)
    assert under > base


def test_check_cooldown_guard_overrides(controller):
    controller.compute_serotonin_signal(2.0)
    controller.set_tacl_guard(lambda name, payload: False)
    assert controller.check_cooldown() is False


def test_step_basic_api(controller):
    """Test the step() API with basic inputs."""
    hold, veto, cooldown_s, level = controller.step(
        stress=1.2, drawdown=-0.03, novelty=0.8
    )
    assert isinstance(hold, bool)
    assert isinstance(veto, bool)
    assert isinstance(cooldown_s, float)
    assert isinstance(level, float)
    assert 0.0 <= level <= 1.0
    assert cooldown_s >= 0.0
    assert hold == veto  # These should be equivalent


def test_step_hold_trigger(controller):
    """Test that step() triggers HOLD when stress is high."""
    # Low stress should not trigger HOLD
    hold1, veto1, _, level1 = controller.step(stress=0.1, drawdown=0.0, novelty=0.1)
    assert not hold1
    assert not veto1
    assert level1 < 0.5

    # High stress should eventually trigger HOLD
    for _ in range(50):
        hold2, veto2, _, level2 = controller.step(
            stress=3.0, drawdown=-0.1, novelty=2.0
        )
    assert hold2 or level2 > controller.config["cooldown_threshold"]


def test_step_cooldown_timer(controller):
    """Test that cooldown timer tracks time correctly."""
    import time as time_module

    # Trigger HOLD by high stress
    for _ in range(50):
        controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    # Check cooldown timer increases
    _, _, cooldown1, _ = controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)
    time_module.sleep(0.1)
    _, _, cooldown2, _ = controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    if cooldown1 > 0 and cooldown2 > 0:
        assert cooldown2 > cooldown1
        assert cooldown2 - cooldown1 >= 0.09  # At least 0.09s difference


def test_step_recovery_after_stress(controller):
    """Test recovery curve after prolonged stress."""
    # Apply stress
    for _ in range(100):
        controller.step(stress=2.5, drawdown=-0.08, novelty=1.5)

    level_high = controller.serotonin_level

    # Apply recovery (low stress)
    for _ in range(100):
        controller.step(stress=0.1, drawdown=-0.01, novelty=0.1)

    level_low = controller.serotonin_level

    # Level should decrease during recovery
    assert level_low < level_high


def test_step_hysteresis(controller):
    """Test hysteresis in HOLD transitions."""
    # Test that HOLD state persists even when serotonin level drops slightly
    # This tests the threshold-based hysteresis in check_cooldown()

    # Build up stress to trigger HOLD
    for _ in range(50):
        controller.step(stress=2.5, drawdown=-0.08, novelty=1.5)

    # Check if we're in HOLD state
    hold1, _, _, level1 = controller.step(stress=2.5, drawdown=-0.08, novelty=1.5)

    # Reduce stress slightly but should still be in HOLD if threshold not crossed
    hold2, _, _, level2 = controller.step(stress=1.8, drawdown=-0.06, novelty=1.0)

    # If we were in HOLD and threshold is high enough, we should still be in HOLD
    # This demonstrates hysteresis at the threshold boundary
    if hold1 and level1 > controller.config["cooldown_threshold"]:
        # With a single step of reduced stress, we might still be above threshold
        if level2 > controller.config["cooldown_threshold"] * 0.95:
            assert hold2  # Should still be in HOLD

    # Now test that sufficient stress reduction exits HOLD
    for _ in range(100):
        controller.step(stress=0.1, drawdown=-0.01, novelty=0.1)

    hold3, _, _, level3 = controller.step(stress=0.1, drawdown=-0.01, novelty=0.1)

    # After sustained low stress, HOLD should be released
    assert not hold3 or level3 > controller.config["cooldown_threshold"] * 1.1


def test_step_validation(controller):
    """Test input validation for step() API."""
    # Negative stress should raise
    with pytest.raises(ValueError):
        controller.step(stress=-1.0, drawdown=-0.05, novelty=0.5)

    # Positive drawdown should raise
    with pytest.raises(ValueError):
        controller.step(stress=1.0, drawdown=0.05, novelty=0.5)

    # Negative novelty should raise
    with pytest.raises(ValueError):
        controller.step(stress=1.0, drawdown=-0.05, novelty=-0.5)


def test_step_with_overrides(controller):
    """Test step() with optional parameter overrides."""
    hold1, _, _, level1 = controller.step(
        stress=1.0,
        drawdown=-0.05,
        novelty=0.5,
        market_vol=2.0,  # Override
        free_energy=1.0,  # Override
        cum_losses=0.1,  # Override
        rho_loss=-0.5,  # Override
    )

    hold2, _, _, level2 = controller.step(
        stress=1.0, drawdown=-0.05, novelty=0.5  # No overrides
    )

    # Results should differ due to overrides
    assert level1 != level2 or hold1 != hold2


def test_step_tacl_telemetry(caplog, controller):
    """Test that step() emits TACL telemetry."""
    caplog.set_level(logging.INFO)
    controller.step(stress=1.5, drawdown=-0.04, novelty=0.9)

    # Check that TACL metrics were logged
    log_text = caplog.text
    assert "tacl.5ht.level" in log_text
    assert "tacl.5ht.hold" in log_text
    assert "tacl.5ht.cooldown" in log_text


def test_step_cooldown_exit(controller):
    """Test cooldown timer resets when exiting HOLD state."""
    # Trigger HOLD
    for _ in range(50):
        controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    hold1, _, cooldown1, _ = controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    # Exit HOLD by reducing stress
    for _ in range(100):
        controller.step(stress=0.05, drawdown=0.0, novelty=0.05)

    hold2, _, cooldown2, _ = controller.step(stress=0.05, drawdown=0.0, novelty=0.05)

    if hold1 and not hold2:
        # Cooldown should be 0 after exiting HOLD
        assert cooldown2 == 0.0


def test_to_dict_includes_cooldown(controller):
    """Test that to_dict() includes cooldown state."""
    controller.step(stress=2.0, drawdown=-0.05, novelty=1.0)
    state = controller.to_dict()

    assert "hold_state" in state
    assert "cooldown_s" in state
    assert isinstance(state["hold_state"], bool)
    assert isinstance(state["cooldown_s"], float)
    assert state["cooldown_s"] >= 0.0


def test_update_metrics_includes_tacl(caplog, controller):
    """Test that update_metrics() emits TACL telemetry."""
    caplog.set_level(logging.INFO)
    controller.step(stress=1.0, drawdown=-0.03, novelty=0.5)
    controller.update_metrics()

    log_text = caplog.text
    assert "tacl.5ht.level" in log_text
    assert "tacl.5ht.hold" in log_text
    assert "tacl.5ht.cooldown" in log_text


def test_step_monotonic_stress_response(controller):
    """Test that higher stress generally leads to higher serotonin levels."""
    levels = []
    stress_values = [0.5, 1.0, 1.5, 2.0, 2.5]

    for stress in stress_values:
        # Reset controller for each test
        controller.tonic_level = 0.0
        controller.sensitivity = 1.0
        # Run multiple steps to let tonic build up
        for _ in range(20):
            _, _, _, level = controller.step(
                stress=stress, drawdown=-0.02, novelty=stress * 0.4
            )
        levels.append(level)

    # Higher stress should generally lead to higher levels
    for i in range(len(levels) - 1):
        assert levels[i] <= levels[i + 1] or levels[i] - levels[i + 1] < 0.1


def test_save_and_load_state(controller, tmp_path):
    """Test state persistence and recovery."""
    # Build up some state
    for _ in range(30):
        controller.step(stress=2.0, drawdown=-0.05, novelty=1.0)

    original_state = controller.to_dict()
    state_file = tmp_path / "serotonin_state.json"

    # Save state
    controller.save_state(str(state_file))
    assert state_file.exists()

    # Reset controller
    controller.reset()
    assert controller.serotonin_level == 0.0
    assert controller.tonic_level == 0.0

    # Load state
    controller.load_state(str(state_file))
    restored_state = controller.to_dict()

    # Verify key state is restored
    assert (
        abs(restored_state["serotonin_level"] - original_state["serotonin_level"])
        < 0.01
    )
    assert abs(restored_state["tonic_level"] - original_state["tonic_level"]) < 0.01
    assert abs(restored_state["sensitivity"] - original_state["sensitivity"]) < 0.01


def test_load_state_file_not_found(controller):
    """Test load_state raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        controller.load_state("/nonexistent/path/state.json")


def test_reset_state(controller):
    """Test reset() restores initial state."""
    # Build up state
    for _ in range(50):
        controller.step(stress=2.5, drawdown=-0.08, novelty=1.5)

    # State should be non-zero
    assert controller.serotonin_level > 0.0
    assert controller.tonic_level > 0.0

    # Reset
    controller.reset()

    # All state should be zeroed
    assert controller.serotonin_level == 0.0
    assert controller.tonic_level == 0.0
    assert controller.sensitivity == 1.0
    assert controller.desens_counter == 0
    assert controller._hold_state is False
    assert controller._step_count == 0


def test_reset_is_total_reset(tmp_path, config_dict):
    """Reset must clear trace, decisions, safety state and timers."""
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)
    controller = SerotoninController(str(cfg_path), logger=lambda *_: None)

    controller.update({"stress": 1.2, "drawdown": -0.05, "novelty": 0.8})
    controller.update({"stress": 1.5, "drawdown": -0.06, "novelty": 0.9})
    assert controller._trace_events
    assert controller._last_decision is not None

    controller.reset()

    assert controller._trace_events == []
    assert controller._last_decision is None
    assert controller._last_event is None
    assert controller._safety_monitor._last_stress is None
    assert controller._safety_monitor._last_budget is None
    assert controller._cooldown_start_time is None
    assert controller._hold_state is False
    assert controller._total_cooldown_time == 0.0
    assert controller._veto_count == 0
    assert controller._step_count == 0
    assert controller.temperature_floor == controller.config["temperature_floor_min"]

    controller.update({"stress": 0.4, "drawdown": -0.02, "novelty": 0.3})
    assert controller._trace_events  # trace restarted cleanly
    assert controller._last_decision is not None


def test_health_check_normal(controller):
    """Test health_check returns healthy status under normal conditions."""
    # Run a few normal steps
    for _ in range(10):
        controller.step(stress=1.0, drawdown=-0.02, novelty=0.5)

    health = controller.health_check()
    assert "healthy" in health
    assert "issues" in health
    assert "warnings" in health
    assert "state" in health
    assert "metrics" in health


def test_health_check_detects_stuck_hold(controller, tmp_path):
    """Test health_check detects stuck HOLD state."""
    # Manually set stuck state (simulate long HOLD)
    controller._hold_state = True
    controller._cooldown_start_time = time() - 3700  # Over 1 hour ago

    health = controller.health_check()
    assert not health["healthy"]
    assert len(health["issues"]) > 0
    assert any("Stuck in HOLD" in issue for issue in health["issues"])


def test_health_check_warns_low_sensitivity(controller):
    """Test health_check warns about low sensitivity."""
    # Force low sensitivity
    controller.sensitivity = 0.15

    health = controller.health_check()
    assert len(health["warnings"]) > 0
    assert any("Low sensitivity" in warning for warning in health["warnings"])


def test_get_performance_metrics(controller):
    """Test performance metrics tracking."""
    # No steps yet
    metrics = controller.get_performance_metrics()
    assert metrics["step_count"] == 0
    assert metrics["veto_count"] == 0
    assert metrics["veto_rate"] == 0.0

    # Run some steps
    for _ in range(20):
        controller.step(stress=1.0, drawdown=-0.02, novelty=0.5)

    # Trigger HOLD
    for _ in range(30):
        controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    metrics = controller.get_performance_metrics()
    assert metrics["step_count"] == 50
    assert metrics["veto_count"] > 0
    assert 0.0 <= metrics["veto_rate"] <= 1.0


def test_diagnose_output(controller):
    """Test diagnose() generates useful output."""
    # Build some state
    for _ in range(20):
        controller.step(stress=1.5, drawdown=-0.04, novelty=0.8)

    report = controller.diagnose()

    # Check report contains key information
    assert "SerotoninController Diagnostic Report" in report
    assert "Serotonin Level:" in report
    assert "HOLD State:" in report
    assert "Performance Metrics:" in report
    assert "Health:" in report


def test_context_manager(controller):
    """Test controller works as context manager."""
    with controller as ctrl:
        assert ctrl is controller
        ctrl.step(stress=1.0, drawdown=-0.02, novelty=0.5)

    # Context manager should not affect state
    assert controller.serotonin_level >= 0.0


def test_repr(controller):
    """Test __repr__ provides useful debug info."""
    repr_str = repr(controller)
    assert "SerotoninController" in repr_str
    assert "level=" in repr_str
    assert "hold=" in repr_str
    assert "steps=" in repr_str


def test_performance_tracking_accuracy(controller):
    """Test performance tracking is accurate."""
    # Run exactly 10 steps
    for i in range(10):
        controller.step(stress=0.5, drawdown=-0.01, novelty=0.3)

    metrics = controller.get_performance_metrics()
    assert metrics["step_count"] == 10

    # Now trigger HOLD
    for i in range(40):
        controller.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    metrics = controller.get_performance_metrics()
    assert metrics["step_count"] == 50

    # Check veto tracking
    if metrics["veto_count"] > 0:
        assert metrics["veto_rate"] == metrics["veto_count"] / metrics["step_count"]


def test_state_persistence_includes_metadata(controller, tmp_path):
    """Test saved state includes metadata."""
    # Run some steps
    for _ in range(25):
        controller.step(stress=1.5, drawdown=-0.03, novelty=0.7)

    state_file = tmp_path / "state_with_metadata.json"
    controller.save_state(str(state_file))

    # Load raw JSON to check metadata
    import json

    with open(state_file, "r") as f:
        state = json.load(f)

    assert "_metadata" in state
    assert "timestamp" in state["_metadata"]
    assert "config_path" in state["_metadata"]
    assert "step_count" in state["_metadata"]
    assert state["_metadata"]["step_count"] == 25


def test_reset_preserves_config(controller):
    """Test reset() preserves configuration."""
    original_alpha = controller.config["alpha"]
    original_threshold = controller.config["cooldown_threshold"]

    # Build state and reset
    for _ in range(20):
        controller.step(stress=2.0, drawdown=-0.05, novelty=1.0)
    controller.reset()

    # Config should be unchanged
    assert controller.config["alpha"] == original_alpha
    assert controller.config["cooldown_threshold"] == original_threshold


def test_health_check_detects_config_issues(controller):
    """Test health_check detects invalid config state."""
    # Manually corrupt config
    controller.config["decay_rate"] = 1.5  # Invalid (should be ≤1.0)

    health = controller.health_check()
    assert not health["healthy"]
    assert any("decay_rate" in issue for issue in health["issues"])


def test_configurable_hysteresis_margin(tmp_path):
    """Test v2.5.0 configurable hysteresis margin feature."""
    config_dict = {
        "alpha": 0.42,
        "beta": 0.28,
        "gamma": 0.32,
        "delta_rho": 0.18,
        "k": 1.0,
        "theta": 0.5,
        "delta": 0.8,
        "za_bias": -0.33,
        "decay_rate": 0.05,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 100,
        "desens_rate": 0.01,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "beta_temper": 0.12,
        "max_desens_counter": 1000,
        "phase_threshold": 0.4,
        "burst_factor": 2.5,
        "mod_t_max": 4.0,
        "mod_t_half": 24.0,
        "mod_k": 0.7,
        "tick_hours": 1.0,
        "phase_kappa": 0.08,
        "desens_gain": 0.12,
        "gate_veto": 0.9,
        "phasic_veto": 1.0,
        "temperature_floor_min": 0.05,
        "temperature_floor_max": 0.4,
        "hysteresis_margin": 0.10,  # Custom 10% hysteresis margin
    }

    cfg_path = tmp_path / "serotonin_hysteresis.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)

    controller = SerotoninController(str(cfg_path))

    # Verify hysteresis margin is loaded from config
    assert controller.config.get("hysteresis_margin", 0.05) == 0.10

    # Test that the controller works with custom hysteresis
    veto = controller.check_cooldown(0.5)  # Below threshold
    assert not veto  # Should not veto at low level


def test_hysteresis_margin_default_value(tmp_path):
    """Test that hysteresis_margin defaults to 0.05 if not specified."""
    config_dict = {
        "alpha": 0.42,
        "beta": 0.28,
        "gamma": 0.32,
        "delta_rho": 0.18,
        "k": 1.0,
        "theta": 0.5,
        "delta": 0.8,
        "za_bias": -0.33,
        "decay_rate": 0.05,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 100,
        "desens_rate": 0.01,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "beta_temper": 0.12,
        "max_desens_counter": 1000,
        "phase_threshold": 0.4,
        "burst_factor": 2.5,
        "mod_t_max": 4.0,
        "mod_t_half": 24.0,
        "mod_k": 0.7,
        "tick_hours": 1.0,
        "phase_kappa": 0.08,
        "desens_gain": 0.12,
        "gate_veto": 0.9,
        "phasic_veto": 1.0,
        "temperature_floor_min": 0.05,
        "temperature_floor_max": 0.4,
        # No hysteresis_margin specified - should default to 0.05
    }

    cfg_path = tmp_path / "serotonin_no_hysteresis.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"active_profile": "v24", "serotonin_v24": config_dict}, f)

    controller = SerotoninController(str(cfg_path))

    # check_cooldown should use default margin of 0.05
    veto = controller.check_cooldown(0.5)
    assert not veto  # Should work with default margin
