from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Optional

import yaml

import pytest

from tradepulse.core.neuro.dopamine import ActionGate, DopamineController
from tradepulse.core.neuro.dopamine.action_gate import (
    DopamineSnapshot,
    GABASnapshot,
    NAACHSnapshot,
    SerotoninSnapshot,
)
from tradepulse.core.neuro.dopamine.ddm_adapter import DDMThresholds, ddm_thresholds


SEROTONIN_TEST_CONFIG = {
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


def _make_dopamine_snapshot(
    controller: DopamineController,
    level: float,
    *,
    release_gate_open: bool = True,
    thresholds: Optional[DDMThresholds] = None,
    temperature: Optional[float] = None,
) -> DopamineSnapshot:
    controller.dopamine_level = level
    base_temp = controller.compute_temperature(level)
    temp = base_temp if temperature is None else float(temperature)
    if thresholds is None:
        go_threshold = float(controller.config["invigoration_threshold"])
        hold_threshold = float(controller.config["hold_threshold"])
        no_go_threshold = float(controller.config["no_go_threshold"])
    else:
        go_threshold = float(thresholds.go_threshold)
        hold_threshold = float(thresholds.hold_threshold)
        no_go_threshold = float(thresholds.no_go_threshold)
    return DopamineSnapshot(
        level=float(level),
        temperature=float(temp),
        go_threshold=go_threshold,
        hold_threshold=hold_threshold,
        no_go_threshold=no_go_threshold,
        release_gate_open=bool(release_gate_open),
    )


def _make_serotonin_snapshot(
    *, level: float = 0.0, hold: bool = False, floor: float = 0.0
) -> SerotoninSnapshot:
    return SerotoninSnapshot(
        level=float(level),
        hold=bool(hold),
        temperature_floor=float(floor),
    )


@pytest.fixture()
def controller(tmp_path: Path) -> DopamineController:
    cfg_target = tmp_path / "dopamine.yaml"
    cfg_target.write_text(Path("config/dopamine.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    ctrl = DopamineController(str(cfg_target))
    ctrl.dopamine_level = 0.7
    return ctrl


def test_gate_respects_release_serotonin_and_gaba(controller: DopamineController) -> None:
    gate = ActionGate(controller)

    serotonin_hold = _make_serotonin_snapshot(hold=True, floor=0.5)
    dopamine_closed = _make_dopamine_snapshot(controller, 0.8, release_gate_open=False)
    eval_closed = gate.evaluate(dopamine=dopamine_closed, serotonin=serotonin_hold)

    assert eval_closed.hold is True
    assert eval_closed.go is False
    assert eval_closed.no_go is True
    assert eval_closed.decision == "NO_GO"
    assert eval_closed.temperature >= 0.5 - 1e-9

    dopamine_open = _make_dopamine_snapshot(controller, 0.8, release_gate_open=True)
    eval_serotonin_hold = gate.evaluate(dopamine=dopamine_open, serotonin=serotonin_hold)
    assert eval_serotonin_hold.hold is True
    assert eval_serotonin_hold.no_go is True

    gaba_block = GABASnapshot(inhibition=0.9, stdp_dw=-0.02)
    serotonin_clear = _make_serotonin_snapshot(hold=False, floor=0.0)
    dopamine_for_gaba = _make_dopamine_snapshot(controller, 0.9, release_gate_open=True)
    eval_gaba = gate.evaluate(
        dopamine=dopamine_for_gaba,
        serotonin=serotonin_clear,
        gaba=gaba_block,
    )

    assert eval_gaba.hold is True
    assert eval_gaba.no_go is True
    assert eval_gaba.decision == "NO_GO"


def test_gate_combines_modulators_for_go_decision(controller: DopamineController) -> None:
    logs: List[tuple[str, float]] = []

    def capture(name: str, value: float) -> None:
        logs.append((name, value))

    gate = ActionGate(controller, logger=capture)
    bounds = controller.temperature_bounds()
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

    dopamine = _make_dopamine_snapshot(
        controller,
        0.95,
        thresholds=thresholds,
        temperature=bounds[1],
    )
    serotonin = _make_serotonin_snapshot(level=0.1, hold=False, floor=0.05)
    gaba = GABASnapshot(inhibition=0.1, stdp_dw=0.07)
    na_ach = NAACHSnapshot(
        arousal=0.6,
        attention=1.8,
        risk_multiplier=1.2,
        temperature_scale=5.0,
    )

    evaluation = gate.evaluate(
        dopamine=dopamine,
        serotonin=serotonin,
        gaba=gaba,
        na_ach=na_ach,
    )

    assert evaluation.go is True
    assert evaluation.hold is False
    assert evaluation.no_go is False
    assert evaluation.decision == "GO"
    assert evaluation.score == pytest.approx(1.0)
    assert bounds[0] <= evaluation.temperature <= bounds[1]
    assert any(name == "tacl.gaba.stdp_dw" for name, _ in logs)


def test_gate_produces_hold_window(controller: DopamineController) -> None:
    gate = ActionGate(controller)

    dopamine = _make_dopamine_snapshot(controller, 0.5)
    serotonin = _make_serotonin_snapshot(hold=False)
    na_ach = NAACHSnapshot(arousal=0.4, attention=1.0, risk_multiplier=1.0, temperature_scale=1.0)

    evaluation = gate.evaluate(dopamine=dopamine, serotonin=serotonin, na_ach=na_ach)

    assert evaluation.go is False
    assert evaluation.no_go is False
    assert evaluation.hold is False
    assert evaluation.decision == "HOLD"
    assert evaluation.score == pytest.approx(0.5, rel=1e-3)


def test_gate_with_real_serotonin_step_api(controller: DopamineController, tmp_path: Path) -> None:
    """Test ActionGate integration with SerotoninController.step() API."""
    serotonin_spec = importlib.util.spec_from_file_location(
        "serotonin_controller",
        Path(__file__).resolve().parents[4] / "core" / "neuro" / "serotonin" / "serotonin_controller.py"
    )
    serotonin_module = importlib.util.module_from_spec(serotonin_spec)
    sys.modules["serotonin_controller_test"] = serotonin_module
    serotonin_spec.loader.exec_module(serotonin_module)
    SerotoninController = serotonin_module.SerotoninController

    sero_cfg = tmp_path / "serotonin.yaml"
    sero_cfg.write_text(yaml.safe_dump(SEROTONIN_TEST_CONFIG), encoding="utf-8")
    serotonin = SerotoninController(str(sero_cfg))

    gate = ActionGate(controller)
    dopamine = _make_dopamine_snapshot(controller, 0.8, release_gate_open=True)

    hold1, veto1, cooldown1, level1 = serotonin.step(stress=0.1, drawdown=-0.01, novelty=0.1)
    sero_snapshot1 = SerotoninSnapshot(
        level=float(level1),
        hold=bool(hold1),
        temperature_floor=float(serotonin.temperature_floor),
    )
    eval1 = gate.evaluate(dopamine=dopamine, serotonin=sero_snapshot1)

    assert sero_snapshot1.hold is False
    assert eval1.go is True
    assert eval1.hold is False

    for _ in range(50):
        serotonin.step(stress=3.0, drawdown=-0.1, novelty=2.0)

    hold2, veto2, cooldown2, level2 = serotonin.step(stress=3.0, drawdown=-0.1, novelty=2.0)
    sero_snapshot2 = SerotoninSnapshot(
        level=float(level2),
        hold=bool(hold2),
        temperature_floor=float(serotonin.temperature_floor),
    )
    eval2 = gate.evaluate(dopamine=dopamine, serotonin=sero_snapshot2)

    if sero_snapshot2.hold:
        assert eval2.hold is True
        assert eval2.go is False
        assert cooldown2 >= 0.0
    assert eval2.temperature >= serotonin.temperature_floor


def test_gate_handles_logger_errors(controller: DopamineController) -> None:
    class ExplodingLogger:
        def __init__(self) -> None:
            self.calls: List[str] = []

        def __call__(self, name: str, value: float) -> None:
            self.calls.append(name)
            raise RuntimeError("boom")

    gate = ActionGate(controller, logger=ExplodingLogger())
    dopamine = _make_dopamine_snapshot(controller, 0.7)
    serotonin = _make_serotonin_snapshot(hold=False)

    result = gate.evaluate(dopamine=dopamine, serotonin=serotonin)

    assert result.decision in {"GO", "HOLD"}
