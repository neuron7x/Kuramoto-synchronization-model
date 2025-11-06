from __future__ import annotations

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
    }


@pytest.fixture
def controller(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(config_dict, f)

    def stub_logger(name: str, value: float) -> None:
        return None

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


def test_serotonin_signal_updates_tonic_and_sensitivity(controller):
    ser1 = controller.compute_serotonin_signal(1.0)
    tonic1 = controller.tonic_level
    assert tonic1 == pytest.approx(0.05 * 1.0, rel=1e-3)

    ser2 = controller.compute_serotonin_signal(1.0)
    tonic2 = controller.tonic_level
    expected_tonic2 = (1 - 0.05) * tonic1 + 0.05 * 1.0
    assert tonic2 == pytest.approx(expected_tonic2, rel=1e-3)

    assert 0.0 <= ser1 <= 1.0
    assert 0.0 <= ser2 <= 1.0
    assert controller.serotonin_level == pytest.approx(ser2, rel=1e-6)


def test_desensitization_and_recovery(controller):
    for _ in range(150):
        controller.compute_serotonin_signal(2.0)
    assert controller.sensitivity < 1.0
    assert controller.sensitivity <= 0.6

    sens_before = controller.sensitivity
    for _ in range(50):
        controller.compute_serotonin_signal(0.1)
    assert controller.sensitivity >= sens_before
    assert controller.sensitivity <= 1.0


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


def test_check_cooldown(controller):
    assert controller.check_cooldown(0.8) is True
    assert controller.check_cooldown(0.6) is False


def test_meta_adapt_increases_weights_on_deep_drawdown(controller):
    cfg_before = controller.config.copy()
    controller.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
    assert controller.config["alpha"] == pytest.approx(cfg_before["alpha"] * 1.01, rel=1e-3)
    assert controller.config["gamma"] == pytest.approx(cfg_before["gamma"] * 1.01, rel=1e-3)


def test_save_and_to_dict(controller, tmp_path):
    controller.config["alpha"] *= 1.05
    out_path = tmp_path / "out_serotonin.yaml"
    controller.save_config_to_yaml(str(out_path))
    assert out_path.exists()
    with open(out_path, "r") as f:
        cfg = yaml.safe_load(f)
    assert cfg["alpha"] == pytest.approx(controller.config["alpha"], rel=1e-6)
    state = controller.to_dict()
    assert "tonic_level" in state
    assert "sensitivity" in state
    assert "alpha" in state
