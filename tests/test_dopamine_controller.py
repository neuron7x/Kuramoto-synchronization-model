from __future__ import annotations

import yaml
import pytest

from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController


@pytest.fixture
def config_dict():
    return {
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
    }


@pytest.fixture
def controller(tmp_path, config_dict):
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    def stub_logger(name: str, value: float) -> None:
        return None

    return DopamineController(str(cfg_path), logger=stub_logger)


def test_estimate_appetitive_state_with_absrpe(controller):
    controller.last_rpe = 0.4
    appetitive = controller.estimate_appetitive_state(1.0, 0.5, 0.2, 0.3)
    cfg = controller.config
    novelty_eff = 0.5 + cfg["c_absrpe"] * abs(0.4)
    expected = (
        cfg["w_r"] * 1.0
        + cfg["w_n"] * novelty_eff
        + cfg["w_m"] * 0.2
        + cfg["w_v"] * 0.3
    )
    assert appetitive == pytest.approx(expected, rel=1e-6)


def test_estimate_appetitive_state_validation(controller):
    with pytest.raises(ValueError):
        controller.estimate_appetitive_state(-0.1, 0.0, 0.0, 0.0)


def test_compute_rpe_and_update_value(controller):
    reward, value, next_value = 0.1, 0.2, 0.5
    rpe = controller.compute_rpe(reward, value, next_value)
    assert rpe == pytest.approx(0.39, rel=1e-6)
    updated_value = controller.update_value_estimate()
    assert updated_value == pytest.approx(0.0 + 0.1 * 0.39, rel=1e-6)


def test_dopamine_signal_updates_tonic_and_phasic(controller):
    appetitive, rpe = 1.0, 0.5
    da1 = controller.compute_dopamine_signal(appetitive, rpe)
    tonic1 = controller.tonic_level
    expected_tonic1 = 0.05 * (appetitive + max(0.0, rpe) * controller.config["burst_factor"])
    assert tonic1 == pytest.approx(expected_tonic1, rel=1e-6)
    assert 0.0 <= da1 <= 1.0
    assert controller.phasic_level == pytest.approx(rpe * controller.config["burst_factor"], rel=1e-6)

    appetitive2, rpe2 = 0.2, 0.0
    da2 = controller.compute_dopamine_signal(appetitive2, rpe2)
    tonic2 = controller.tonic_level
    expected_tonic2 = (1 - 0.05) * tonic1 + 0.05 * (appetitive2 + 0.0)
    assert tonic2 == pytest.approx(expected_tonic2, rel=1e-6)
    assert 0.0 <= da2 <= 1.0


def test_temperature_behaviour(controller):
    da_low = controller.compute_dopamine_signal(0.1, 0.0)
    t_low = controller.compute_temperature(da_low)

    da_high = controller.compute_dopamine_signal(1.2, 0.7)
    t_high = controller.compute_temperature(da_high)

    assert t_high < t_low

    controller.last_rpe = -0.8
    t_neg = controller.compute_temperature(da_high)
    assert t_neg >= t_high


def test_modulate_action_value(controller):
    q = 2.0
    da = 0.8
    cfg = controller.config
    q_mod = controller.modulate_action_value(q, dopamine_signal=da)
    expected = q * (1.0 + cfg["delta_gain"] * (da - cfg["baseline"]))
    assert q_mod == pytest.approx(expected, rel=1e-6)


def test_go_no_go(controller):
    assert controller.check_invigoration(0.8) is True
    assert controller.check_invigoration(0.6) is False
    assert controller.check_suppress(0.2) is True
    assert controller.check_suppress(0.4) is False


def test_meta_adapt_good_and_bad(controller):
    cfg0 = dict(controller.config)
    controller.meta_adapt({"drawdown": -0.04, "sharpe": 1.1})
    assert controller.config["learning_rate_v"] == pytest.approx(cfg0["learning_rate_v"] * 1.01, rel=1e-6)
    assert controller.config["delta_gain"] == pytest.approx(cfg0["delta_gain"] * 1.01, rel=1e-6)
    assert controller.config["base_temperature"] == pytest.approx(cfg0["base_temperature"] * 0.99, rel=1e-6)

    cfg1 = dict(controller.config)
    controller.meta_adapt({"drawdown": -0.10, "sharpe": 0.6})
    assert controller.config["learning_rate_v"] == pytest.approx(cfg1["learning_rate_v"] * 0.99, rel=1e-6)
    assert controller.config["delta_gain"] == pytest.approx(cfg1["delta_gain"] * 0.99, rel=1e-6)
    assert controller.config["base_temperature"] == pytest.approx(cfg1["base_temperature"] * 1.01, rel=1e-6)


def test_save_and_to_dict(controller, tmp_path):
    controller.compute_rpe(0.2, 0.1, 0.3)
    controller.update_value_estimate()
    controller.compute_dopamine_signal(0.9, 0.4)

    out_path = tmp_path / "out_dopamine.yaml"
    controller.save_config_to_yaml(str(out_path))
    assert out_path.exists()

    with open(out_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert "discount_gamma" in cfg

    state = controller.to_dict()
    for key in ["tonic_level", "phasic_level", "dopamine_level", "value_estimate", "last_rpe"]:
        assert key in state
