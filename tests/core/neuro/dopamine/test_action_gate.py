from __future__ import annotations

import math
from pathlib import Path

import pytest

from tradepulse.core.neuro.dopamine import ActionGate, DopamineController
from tradepulse.core.neuro.dopamine.ddm_adapter import DDMThresholds, ddm_thresholds


class DummySerotonin:
    def __init__(self, hold: bool = False, floor: float = 0.0) -> None:
        self._hold = hold
        self.temperature_floor = floor

    def check_cooldown(self, serotonin_signal=None) -> bool:  # pragma: no cover - signature parity
        return self._hold


@pytest.fixture()
def controller(tmp_path: Path) -> DopamineController:
    cfg_target = tmp_path / "dopamine.yaml"
    cfg_target.write_text(Path("config/dopamine.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    ctrl = DopamineController(str(cfg_target))
    ctrl.dopamine_level = 0.7
    return ctrl


def test_gate_respects_release_and_hold(controller: DopamineController) -> None:
    serotonin = DummySerotonin(hold=True)
    gate = ActionGate(controller, serotonin)
    eval_hold = gate.evaluate(dopamine_signal=0.8, release_gate_open=False)
    assert eval_hold.hold is True
    assert eval_hold.go is False
    assert eval_hold.no_go is True


def test_gate_temperature_scaling(controller: DopamineController) -> None:
    thresholds = ddm_thresholds(
        1.2,
        controller.config["ddm_baseline_a"],
        controller.config["ddm_baseline_t0"],
        temp_gain=controller.config["ddm_temp_gain"],
        threshold_gain=controller.config["ddm_threshold_gain"],
        hold_gain=controller.config["ddm_hold_gain"],
        min_temp_scale=controller.config["ddm_min_temperature_scale"],
        max_temp_scale=controller.config["ddm_max_temperature_scale"],
        baseline_a=controller.config["ddm_baseline_a"],
        baseline_t0=controller.config["ddm_baseline_t0"],
        eps=controller.config["ddm_eps"],
    )
    gate = ActionGate(controller, DummySerotonin(floor=0.02))
    base_temp = controller.compute_temperature(0.6)
    eval_scaled = gate.evaluate(
        dopamine_signal=0.6,
        thresholds=thresholds,
        release_gate_open=True,
    )
    assert eval_scaled.temperature <= controller.temperature_bounds()[1]
    assert eval_scaled.temperature <= base_temp + 1e-8
    assert eval_scaled.temperature >= controller.temperature_bounds()[0]
    assert isinstance(thresholds, DDMThresholds)


def test_gate_balances_hold_and_go(controller: DopamineController) -> None:
    serotonin = DummySerotonin(hold=False)
    gate = ActionGate(controller, serotonin)
    eval_decision = gate.evaluate(dopamine_signal=0.9, release_gate_open=True)

    assert eval_decision.go is True
    assert eval_decision.hold is False
    assert eval_decision.no_go is False
    assert math.isfinite(eval_decision.temperature)

    eval_hold = gate.evaluate(dopamine_signal=0.1, release_gate_open=True)
    assert eval_hold.no_go is True
    assert eval_hold.hold is True
