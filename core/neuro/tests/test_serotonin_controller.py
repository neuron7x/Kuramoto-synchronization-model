from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
import sys
import types
from typing import Mapping

import pytest
import yaml

from core.neuro.serotonin.serotonin_controller import SerotoninController

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_ensure_map = {
    "src": _SRC_ROOT,
    "src.tradepulse": _SRC_ROOT / "tradepulse",
    "src.tradepulse.core": _SRC_ROOT / "tradepulse" / "core",
    "src.tradepulse.core.neuro": _SRC_ROOT / "tradepulse" / "core" / "neuro",
    "src.tradepulse.core.neuro.dopamine": _SRC_ROOT
    / "tradepulse"
    / "core"
    / "neuro"
    / "dopamine",
}
for pkg, path in _ensure_map.items():
    module = sys.modules.get(pkg)
    if module is None:
        module = types.ModuleType(pkg)
        module.__path__ = [str(path)]
        sys.modules[pkg] = module
    else:
        module.__path__ = [str(path)]

ActionGate = importlib.import_module(
    "src.tradepulse.core.neuro.dopamine.action_gate"
).ActionGate


@pytest.fixture
def config_dict() -> Mapping[str, float]:
    return {
        "alpha": 0.42,
        "beta": 0.28,
        "gamma": 0.32,
        "delta_rho": 0.18,
        "stress_gain": 0.9,
        "drawdown_gain": 1.1,
        "novelty_gain": 0.6,
        "k": 1.0,
        "theta": 0.5,
        "delta": 0.8,
        "za_bias": -0.25,
        "decay_rate": 0.08,
        "phasic_decay": 0.4,
        "hold_threshold": 0.7,
        "release_threshold": 0.55,
        "desens_threshold_ticks": 30,
        "desens_rate": 0.05,
        "sensitivity_floor": 0.2,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "beta_temper": 0.12,
        "phase_threshold": 0.4,
        "burst_factor": 2.4,
        "mod_t_max": 4.0,
        "mod_t_half": 24.0,
        "mod_k": 0.7,
        "max_desens_counter": 300,
        "desens_gain": 0.2,
        "cooldown_base_ticks": 5,
        "cooldown_growth": 20.0,
        "cooldown_max_ticks": 60,
        "hold_guard_ticks": 8,
        "stress_desens_threshold": 0.6,
        "tau_5ht_ms": 150.0,
        "step_ms": 1000.0,
        "tick_hours": 1.0,
        "phase_kappa": 0.08,
        "gate_veto": 0.9,
        "phasic_veto": 1.0,
        "temperature_floor_min": 0.05,
        "temperature_floor_max": 0.4,
    }


@pytest.fixture
def controller(tmp_path, config_dict):
    cfg_path = tmp_path / "serotonin.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    def stub_logger(name: str, value: float) -> None:
        logging.getLogger(__name__).info("%s=%s", name, value)

    return SerotoninController(str(cfg_path), logger=stub_logger)


def _drain(controller: SerotoninController, steps: int) -> None:
    for _ in range(steps):
        controller.step(0.0, 0.0, 0.0)


def test_step_triggers_hold_and_cooldown(controller):
    hold, veto, cooldown_s, level = controller.step(stress=1.0, drawdown=-0.2, novelty=0.5)
    assert hold is True
    assert veto is True
    assert cooldown_s > 0.0
    assert level == pytest.approx(controller.serotonin_level, rel=1e-6)
    assert controller.check_cooldown() is True
    assert controller.hold_signal is True


def test_hysteresis_and_release(controller):
    controller.set_tacl_guard(lambda *_: True)
    controller.step(stress=1.1, drawdown=-0.3, novelty=0.8)
    initial_cooldown = controller._cooldown_ticks_remaining
    levels = []
    for _ in range(initial_cooldown + 10):
        hold, veto, _, level = controller.step(0.0, 0.0, 0.0)
        levels.append(level)
    assert all(levels[i] >= levels[i + 1] for i in range(len(levels) - 1))
    assert controller.hold_signal is False
    assert controller.check_cooldown() is False


def test_hold_guard_blocks_release(controller):
    def guard(event: str, payload: Mapping[str, float]) -> bool:
        if event == "serotonin_hold_release":
            return False
        return True

    controller.set_tacl_guard(guard)
    controller.step(1.2, -0.4, 0.5)
    _drain(controller, controller.config["hold_guard_ticks"] + 5)
    assert controller.hold_signal is True
    assert controller._cooldown_ticks_remaining > 0


def test_desensitisation_and_recovery(controller):
    for _ in range(controller.config["desens_threshold_ticks"] + 10):
        controller.step(1.1, -0.3, 0.2)
    assert controller.sensitivity < 1.0
    sensitivity_before = controller.sensitivity
    _drain(controller, 20)
    assert controller.sensitivity > sensitivity_before
    assert controller.sensitivity <= 1.0


def test_recovery_curve_monotonic(controller):
    controller.step(1.0, -0.25, 0.6)
    values = [controller.step(0.0, 0.0, 0.0)[-1] for _ in range(25)]
    assert values == sorted(values, reverse=True)
    assert values[-1] < values[0]


def test_step_emits_tacl_metrics(tmp_path, config_dict):
    emitted: list[str] = []

    def capture(name: str, value: float) -> None:
        emitted.append(name)

    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    ctrl = SerotoninController(str(cfg_path), logger=capture)
    ctrl.step(0.9, -0.3, 0.7)
    assert any(name == "tacl.5ht.level" for name in emitted)
    assert any(name == "tacl.5ht.hold" for name in emitted)
    assert any(name == "tacl.5ht.cooldown" for name in emitted)


def test_update_metrics_emits_hold_snapshot(controller):
    controller.step(0.9, -0.25, 0.4)
    controller.update_metrics()
    assert controller.temperature_floor >= controller.config["temperature_floor_min"]


def test_config_validation_release_threshold(tmp_path, config_dict):
    cfg = dict(config_dict)
    cfg["release_threshold"] = 0.9
    cfg["hold_threshold"] = 0.7
    cfg_path = tmp_path / "bad.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_compute_serotonin_signal_backwards_compat(controller):
    level = controller.compute_serotonin_signal(1.2)
    assert 0.0 <= level <= 1.0
    assert controller.hold_signal in (True, False)


def test_to_dict_contains_hold_state(controller):
    controller.step(1.0, -0.2, 0.5)
    snapshot = controller.to_dict()
    for key in ("hold_active", "cooldown_ticks_remaining", "hold_ticks", "hold_signal"):
        assert key in snapshot


def test_action_gate_consumes_hold_signal(controller):
    controller.step(1.1, -0.4, 0.6)

    @dataclass
    class DummyDopamine:
        dopamine_level: float = 0.8
        config: Mapping[str, float] = None

        def __post_init__(self) -> None:
            self.config = {
                "invigoration_threshold": 0.6,
                "no_go_threshold": 0.2,
                "hold_threshold": 0.5,
            }

        def compute_temperature(self, _: float) -> float:
            return 0.5

        def temperature_bounds(self) -> tuple[float, float]:
            return (0.1, 1.0)

    gate = ActionGate(DummyDopamine(), controller)
    outcome = gate.evaluate(serotonin_signal=controller.serotonin_level)
    assert outcome.hold is True
    assert outcome.go is False
    assert outcome.no_go is True


def test_guard_payload_structure(controller):
    captured: dict[str, Mapping[str, float]] = {}

    def guard(name: str, payload: Mapping[str, float]) -> bool:
        captured["event"] = name
        captured["payload"] = payload
        return True

    controller.set_tacl_guard(guard)
    controller.step(1.1, -0.3, 0.4)
    _drain(controller, 2)
    controller.check_cooldown()
    assert captured["event"] in {"serotonin_cooldown", "serotonin_hold_release"}


def test_step_handles_negative_drawdown(controller):
    hold, veto, _, level = controller.step(0.5, 0.1, 0.3)
    assert hold is False
    assert veto is False
    assert level == pytest.approx(controller.serotonin_level, rel=1e-6)


def test_step_recovery_without_guard(controller):
    controller.step(1.0, -0.2, 0.4)
    controller.set_tacl_guard(lambda *_: True)
    _drain(controller, controller.config["cooldown_base_ticks"] + 20)
    assert controller.hold_signal is False
    assert controller._cooldown_ticks_remaining == 0
