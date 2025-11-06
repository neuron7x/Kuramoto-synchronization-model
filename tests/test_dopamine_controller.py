from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import pytest
import yaml

from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController


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
    cfg = {"discount_gamma": 0.9}
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    with pytest.raises(ValueError):
        DopamineController(str(cfg_path))


def test_configuration_validation_ranges(tmp_path, config_dict: Dict[str, object]) -> None:
    config_dict["delta_gain"] = 1.5
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)
    with pytest.raises(ValueError):
        DopamineController(str(cfg_path))


def test_estimate_appetitive_state_with_abs_rpe(controller: DopamineController) -> None:
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


def test_appetitive_state_rejects_negative(controller: DopamineController) -> None:
    with pytest.raises(ValueError):
        controller.estimate_appetitive_state(-0.1, 0.0, 0.0, 0.0)


def test_compute_rpe_sign_and_magnitude(controller: DopamineController) -> None:
    reward, value, next_value = 0.1, 0.2, 0.5
    rpe = controller.compute_rpe(reward, value, next_value)
    assert math.copysign(1.0, rpe) == math.copysign(1.0, 0.39)
    assert rpe == pytest.approx(0.39, rel=1e-6)
    updated_value = controller.update_value_estimate()
    assert updated_value == pytest.approx(0.0 + 0.1 * 0.39, rel=1e-6)


def test_dopamine_signal_clamped_and_stable(controller: DopamineController) -> None:
    controller.compute_rpe(1e6, 0.0, 0.0)
    high = controller.compute_dopamine_signal(5.0, controller.last_rpe)
    assert 0.0 <= high <= 1.0
    controller.compute_rpe(-1e6, 0.0, 0.0)
    low = controller.compute_dopamine_signal(0.0, controller.last_rpe)
    assert 0.0 <= low <= 1.0


def test_temperature_monotonic_decrease(controller: DopamineController) -> None:
    readings = []
    for appetitive, rpe in ((0.1, 0.0), (0.5, 0.2), (1.0, 0.8)):
        controller.compute_rpe(rpe, 0.0, 0.0)
        da = controller.compute_dopamine_signal(appetitive, rpe)
        readings.append(controller.compute_temperature(da))
    assert readings[0] >= readings[1] >= readings[2]


def test_negative_rpe_increases_temperature(controller: DopamineController) -> None:
    controller.compute_rpe(0.0, 0.0, 0.0)
    da = controller.compute_dopamine_signal(0.5, 0.0)
    base_temp = controller.compute_temperature(da)
    controller.last_rpe = -0.8
    hotter = controller.compute_temperature(da)
    assert hotter >= base_temp


def test_modulate_action_value(controller: DopamineController) -> None:
    q_mod = controller.modulate_action_value(2.0, dopamine_signal=0.8)
    cfg = controller.config
    expected = 2.0 * (1.0 + cfg["delta_gain"] * (0.8 - cfg["baseline"]))
    assert q_mod == pytest.approx(expected, rel=1e-6)


def test_go_no_go_thresholds(controller: DopamineController) -> None:
    assert controller.check_invigoration(0.8) is True
    assert controller.check_invigoration(0.6) is False
    assert controller.check_suppress(0.2) is True
    assert controller.check_suppress(0.4) is False


def test_meta_adapt_respects_cooldown(controller: DopamineController) -> None:
    cfg_snapshot = {
        "learning_rate_v": controller.config["learning_rate_v"],
        "delta_gain": controller.config["delta_gain"],
        "base_temperature": controller.config["base_temperature"],
    }
    controller.meta_adapt({"drawdown": -0.03, "sharpe": 1.2})
    assert controller.config["learning_rate_v"] > cfg_snapshot["learning_rate_v"]
    controller.meta_adapt({"drawdown": -0.10, "sharpe": 0.2})
    assert controller.config["learning_rate_v"] > cfg_snapshot["learning_rate_v"]
    controller._meta_cooldown_counter = 0
    controller.meta_adapt({"drawdown": -0.10, "sharpe": 0.2})
    assert controller.config["learning_rate_v"] < cfg_snapshot["learning_rate_v"]


def test_reset_and_state_roundtrip(controller: DopamineController) -> None:
    controller.compute_rpe(0.2, 0.1, 0.3)
    controller.update_value_estimate()
    controller.compute_dopamine_signal(0.9, 0.4)
    state = controller.dump_state()
    controller.reset_state()
    assert controller.dump_state() == {
        "tonic_level": 0.0,
        "phasic_level": 0.0,
        "dopamine_level": 0.0,
        "value_estimate": 0.0,
        "last_rpe": 0.0,
    }
    controller.load_state(state)
    assert controller.dump_state() == state


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
    for key in ("tonic_level", "phasic_level", "dopamine_level", "value_estimate", "last_rpe"):
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
