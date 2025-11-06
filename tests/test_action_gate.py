from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pytest
import yaml

from tradepulse.core.neuro.dopamine import ActionGate, DopamineController


@dataclass
class SerotoninStub:
    hold: bool
    temperature_floor: float = 0.2

    def check_cooldown(self, _: Optional[float] = None) -> bool:
        return self.hold


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
        "novelty_mode": "external",
        "c_absrpe": 0.10,
        "baseline": 0.5,
        "delta_gain": 0.5,
        "base_temperature": 1.0,
        "min_temperature": 0.05,
        "temp_k": 1.2,
        "neg_rpe_temp_gain": 0.5,
        "max_temp_multiplier": 3.0,
        "invigoration_threshold": 0.6,
        "no_go_threshold": 0.3,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "meta_cooldown_ticks": 0,
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
    return DopamineController(str(cfg_path))


def test_high_dopamine_with_high_serotonin(controller: DopamineController) -> None:
    controller.dopamine_level = 0.9
    gate = ActionGate(controller, SerotoninStub(hold=True, temperature_floor=0.4))
    eval_result = gate.evaluate()
    assert eval_result.go is False
    assert eval_result.hold is True
    assert eval_result.no_go is True
    assert eval_result.temperature >= 0.4


def test_high_dopamine_low_serotonin(controller: DopamineController) -> None:
    controller.dopamine_level = 0.9
    gate = ActionGate(controller, SerotoninStub(hold=False, temperature_floor=0.1))
    eval_result = gate.evaluate()
    assert eval_result.go is True
    assert eval_result.hold is False
    assert eval_result.no_go is False


def test_low_dopamine_high_serotonin(controller: DopamineController) -> None:
    controller.dopamine_level = 0.2
    gate = ActionGate(controller, SerotoninStub(hold=True, temperature_floor=0.3))
    eval_result = gate.evaluate()
    assert eval_result.go is False
    assert eval_result.no_go is True
