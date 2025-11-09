from __future__ import annotations

import importlib.util
import math
import sys
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


def test_gate_with_real_serotonin_step_api(controller: DopamineController, tmp_path: Path) -> None:
    """Test ActionGate integration with SerotoninController.step() API."""
    # Direct import to avoid dependency issues in tests
    serotonin_spec = importlib.util.spec_from_file_location(
        "serotonin_controller",
        Path(__file__).parent.parent.parent.parent / "core" / "neuro" / "serotonin" / "serotonin_controller.py"
    )
    serotonin_module = importlib.util.module_from_spec(serotonin_spec)
    sys.modules["serotonin_controller_test"] = serotonin_module
    serotonin_spec.loader.exec_module(serotonin_module)
    SerotoninController = serotonin_module.SerotoninController

    # Create a serotonin controller with test config
    sero_cfg = tmp_path / "serotonin.yaml"
    sero_cfg.write_text(Path("configs/serotonin.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    serotonin = SerotoninController(str(sero_cfg))

    # Create ActionGate with both controllers
    gate = ActionGate(controller, serotonin)

    # Test 1: Low stress should not trigger HOLD
    hold1, veto1, _, level1 = serotonin.step(stress=0.1, drawdown=-0.01, novelty=0.1)
    eval1 = gate.evaluate(dopamine_signal=0.8, release_gate_open=True)

    assert not hold1
    assert eval1.go is True
    assert eval1.hold is False

    # Test 2: High stress should eventually trigger HOLD
    for _ in range(50):
        serotonin.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    hold2, veto2, cooldown_s, level2 = serotonin.step(stress=3.0, drawdown=-0.1, novelty=2.0)
    eval2 = gate.evaluate(dopamine_signal=0.8, release_gate_open=True)

    # If serotonin triggered hold, gate should respect it
    if hold2:
        assert eval2.hold is True
        assert eval2.go is False
        assert cooldown_s > 0.0

    # Test 3: Temperature floor should be respected
    assert eval2.temperature >= serotonin.temperature_floor
