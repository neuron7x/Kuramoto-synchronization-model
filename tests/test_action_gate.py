from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pytest
import yaml

from core.neuro.serotonin.serotonin_controller import CooldownStatus
from tradepulse.core.neuro.dopamine import ActionGate, DopamineController
from tradepulse.core.neuro.dopamine.ddm_adapter import DDMAdjustment


@dataclass
class SerotoninStub:
    hold: bool
    temperature_floor: float = 0.2
    serotonin_level: float = 0.5
    tonic_trigger: bool = True
    gate_trigger: bool = False
    phasic_trigger: bool = False
    accepted: bool = True

    def check_cooldown(self, _: Optional[float] = None) -> bool:  # pragma: no cover - legacy path
        return self.hold

    def cooldown_status(self, serotonin_signal: Optional[float] = None) -> CooldownStatus:
        return CooldownStatus(
            hold=self.hold,
            tonic_trigger=self.tonic_trigger,
            gate_trigger=self.gate_trigger,
            phasic_trigger=self.phasic_trigger,
            accepted=self.accepted,
            serotonin_level=self.serotonin_level if serotonin_signal is None else float(serotonin_signal),
        )


@pytest.fixture
def config_dict() -> Dict[str, object]:
    return {
        "version": "2.3.0",
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
    assert eval_result.hold_reason == "tonic"


def test_high_dopamine_low_serotonin(controller: DopamineController) -> None:
    controller.dopamine_level = 0.9
    gate = ActionGate(controller, SerotoninStub(hold=False, temperature_floor=0.1))
    eval_result = gate.evaluate()
    assert eval_result.go is True
    assert eval_result.hold is False
    assert eval_result.no_go is False
    assert eval_result.ddm_adjustment is None


def test_low_dopamine_high_serotonin(controller: DopamineController) -> None:
    controller.dopamine_level = 0.2
    gate = ActionGate(controller, SerotoninStub(hold=True, temperature_floor=0.3))
    eval_result = gate.evaluate()
    assert eval_result.go is False
    assert eval_result.no_go is True
    assert eval_result.hold_reason == "tonic"


def test_ddm_adjustment_includes_serotonin_hold(controller: DopamineController) -> None:
    controller.dopamine_level = 0.75
    gate = ActionGate(controller, SerotoninStub(hold=True, temperature_floor=0.2, serotonin_level=0.8))
    result = gate.evaluate(ddm_base_drift=0.5, ddm_base_boundary=1.2, ddm_kwargs={"drift_gain": 0.2})
    assert isinstance(result.ddm_adjustment, DDMAdjustment)
    assert result.ddm_adjustment.drift < 0.5
    assert result.ddm_adjustment.boundary > 1.2


def test_gate_extras_include_tonic_ratio(controller: DopamineController) -> None:
    controller.compute_rpe(0.2, 0.0, 0.0)
    controller.compute_dopamine_signal(0.6, controller.last_rpe)
    gate = ActionGate(controller, None)
    result = gate.evaluate(ddm_base_drift=0.4, ddm_base_boundary=1.0)
    assert result.extras is not None
    assert "tonic_to_phasic_ratio" in result.extras
    assert isinstance(result.ddm_adjustment, DDMAdjustment)
