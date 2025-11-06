from __future__ import annotations

import logging
import math
import numpy as np
import pytest
import yaml

from core.neuro.serotonin.serotonin_controller import SerotoninController


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
        "tau_5ht_ms": 0.0,
        "step_ms": 0.0,
        "tick_hours": 1.0,
        "phase_kappa": 0.08,
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


def test_tau_to_decay_derivation(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    config_dict["tau_5ht_ms"] = 150.0
    config_dict["step_ms"] = 1000.0
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    controller = SerotoninController(str(cfg_path), logger=lambda *_: None)
    expected = 1.0 - math.exp(-1000.0 / 150.0)
    assert controller.config["decay_rate"] == pytest.approx(expected, rel=1e-6)
