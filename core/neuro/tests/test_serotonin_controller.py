from __future__ import annotations

import json
import logging
import math
from time import perf_counter

import numpy as np
import pytest
import yaml
from typing import Mapping

from core.neuro.serotonin.serotonin_controller import (
    SerotoninController,
    _generate_config_table,
    SerotoninConfig,
)


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
    }


@pytest.fixture
def controller(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

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
    expected = 0.42 * 1.0 + 0.28 * 0.5 + 0.32 * 0.2 + 0.18 * (1 - (-0.90))
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
    expected = 0.9 * (1 - 0.6 * 0.8) * (1 + (-0.33))
    expected = float(np.clip(expected, 0.0, 1.0))
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
    expected = grad * (1 - 0.12 * ser)
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
        yaml.safe_dump(cfg, f)
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_env_config_dir_fallback(tmp_path, config_dict, monkeypatch):
    env_dir = tmp_path / "envcfg"
    env_dir.mkdir()
    cfg_path = env_dir / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)
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
            yaml.safe_dump(cfg, f)
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
    responses = [controller.compute_serotonin_signal(val) for val in np.linspace(0, 3, 15)]
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
        yaml.safe_dump(config_dict, f)
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
        yaml.safe_dump(config_dict, f)

    controller = SerotoninController(str(cfg_path), logger=lambda *_: None)
    expected = 1.0 - math.exp(-1000.0 / 150.0)
    assert controller.config["decay_rate"] == pytest.approx(expected, rel=1e-6)


def test_phase_gate_monotonic_around_threshold(tmp_path, config_dict):
    cfg_path = tmp_path / "s.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)
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
        yaml.safe_dump(slow_cfg, f)
    with open(fast_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(fast_cfg, f)

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
