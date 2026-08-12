# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest
import yaml


def _load_serotonin_cls():
    module_path = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "geosync"
        / "core"
        / "neuro"
        / "serotonin"
        / "serotonin_controller.py"
    )
    spec = importlib.util.spec_from_file_location("serotonin_receptor_module", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.SerotoninController


def _config_with_receptors(
    tmp_path: Path, *, enabled: bool, enabled_list: list[str] | None = None
) -> Path:
    cfg_source = Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml"
    cfg = yaml.safe_load(cfg_source.read_text(encoding="utf-8")) or {}
    cfg.setdefault("active_profile", "v24")
    cfg.setdefault("serotonin_v24", {})
    cfg["serotonin_v24"]["receptors"] = {
        "enabled": enabled,
        "enabled_list": enabled_list or [],
    }
    target = tmp_path / ("serotonin_enabled.yaml" if enabled else "serotonin_disabled.yaml")
    target.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return target


@pytest.fixture(scope="module")
def serotonin_cls():
    return _load_serotonin_cls()


def test_receptors_off_equivalence(serotonin_cls, tmp_path: Path):
    cfg_off = _config_with_receptors(tmp_path, enabled=False)
    cfg_empty = _config_with_receptors(tmp_path, enabled=True, enabled_list=[])
    ctrl_off = serotonin_cls(str(cfg_off))
    ctrl_empty = serotonin_cls(str(cfg_empty))
    sequence = [
        (0.2, -0.01, 0.05),
        (0.25, -0.02, 0.1),
        (0.3, -0.015, 0.08),
    ]
    for stress, drawdown, novelty in sequence:
        res_off = ctrl_off.step(stress=stress, drawdown=drawdown, novelty=novelty, dt=1.0)
        res_empty = ctrl_empty.step(stress=stress, drawdown=drawdown, novelty=novelty, dt=1.0)
        assert res_off.hold == res_empty.hold
        assert res_off.veto == res_empty.veto
        assert math.isclose(res_off.level, res_empty.level, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(
            res_off.temperature_floor, res_empty.temperature_floor, rel_tol=1e-9, abs_tol=1e-9
        )


def test_ht3_alarm_triggers_veto_lane(serotonin_cls, tmp_path: Path):
    cfg_alarm = _config_with_receptors(tmp_path, enabled=True, enabled_list=["5ht3"])
    cfg_base = _config_with_receptors(tmp_path, enabled=False)
    ctrl_alarm = serotonin_cls(str(cfg_alarm))
    ctrl_base = serotonin_cls(str(cfg_base))

    ctrl_alarm.step(stress=0.05, drawdown=-0.01, novelty=0.05, dt=1.0)
    ctrl_base.step(stress=0.05, drawdown=-0.01, novelty=0.05, dt=1.0)

    alarm = ctrl_alarm.step(stress=0.6, drawdown=-0.02, novelty=0.1, dt=1.0)
    baseline = ctrl_base.step(stress=0.6, drawdown=-0.02, novelty=0.1, dt=1.0)

    assert baseline.hold is False
    assert alarm.hold is True
    assert alarm.veto is True
    trace = ctrl_alarm.get_last_receptor_trace()
    assert trace is not None
    for act in trace["activations"].values():
        assert 0.0 <= act <= 1.0


def test_ht2c_risk_clamp_monotonic_budget(serotonin_cls, tmp_path: Path):
    cfg = _config_with_receptors(tmp_path, enabled=True, enabled_list=["5ht2c"])
    ctrl = serotonin_cls(str(cfg))

    budgets = []
    for dd in (-0.02, -0.05, -0.08):
        result = ctrl.update({"stress": 0.4, "drawdown": dd, "novelty": 0.4})
        budgets.append(result.risk_budget)
    assert budgets[1] <= budgets[0] + 1e-9
    assert budgets[2] <= budgets[1] + 1e-9


def test_ht1a_widens_hysteresis_reduces_chatter(serotonin_cls, tmp_path: Path):
    cfg_on = _config_with_receptors(tmp_path, enabled=True, enabled_list=["5ht1a"])
    cfg_off = _config_with_receptors(tmp_path, enabled=False)
    ctrl_on = serotonin_cls(str(cfg_on))
    ctrl_off = serotonin_cls(str(cfg_off))

    stress_series = [0.68, 0.72, 0.69, 0.71, 0.7, 0.69, 0.72]
    flips_on = flips_off = 0
    prev_hold_on = prev_hold_off = False
    for s in stress_series:
        res_on = ctrl_on.step(stress=s, drawdown=-0.01, novelty=0.05, dt=1.0)
        res_off = ctrl_off.step(stress=s, drawdown=-0.01, novelty=0.05, dt=1.0)
        if res_on.hold != prev_hold_on:
            flips_on += 1
        if res_off.hold != prev_hold_off:
            flips_off += 1
        prev_hold_on, prev_hold_off = res_on.hold, res_off.hold
    assert flips_on <= flips_off


def test_receptor_enabled_path_deterministic(serotonin_cls, tmp_path: Path):
    cfg = _config_with_receptors(tmp_path, enabled=True, enabled_list=["5ht2a", "5ht7"])
    ctrl = serotonin_cls(str(cfg))
    seq = [
        {"stress": 0.3, "drawdown": -0.02, "novelty": 0.2},
        {"stress": 0.35, "drawdown": -0.03, "novelty": 0.25},
        {"stress": 0.32, "drawdown": -0.025, "novelty": 0.22},
    ]
    outputs_first = [ctrl.step(dt=1.0, **s) for s in seq]
    ctrl.reset()
    outputs_second = [ctrl.step(dt=1.0, **s) for s in seq]
    for first, second in zip(outputs_first, outputs_second):
        assert first.hold == second.hold
        assert first.veto == second.veto
        assert math.isclose(first.level, second.level, rel_tol=1e-9, abs_tol=1e-9)
