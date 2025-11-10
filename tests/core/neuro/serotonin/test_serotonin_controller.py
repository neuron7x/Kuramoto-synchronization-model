from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest


def _load_serotonin_module() -> tuple[object, object]:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "core"
        / "neuro"
        / "serotonin"
        / "serotonin_controller.py"
    )
    spec = importlib.util.spec_from_file_location("serotonin_controller_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, module.SerotoninController


@pytest.fixture(scope="module")
def serotonin_module_and_cls():
    return _load_serotonin_module()


@pytest.fixture()
def serotonin_module(serotonin_module_and_cls):
    module, _ = serotonin_module_and_cls
    return module


@pytest.fixture()
def serotonin_cls(serotonin_module_and_cls):
    _, cls = serotonin_module_and_cls
    return cls


@pytest.fixture()
def serotonin_config_path(tmp_path: Path) -> Path:
    cfg_source = Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml"
    target = tmp_path / "serotonin.yaml"
    target.write_text(cfg_source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture()
def serotonin_controller(serotonin_cls, serotonin_config_path):
    return serotonin_cls(str(serotonin_config_path))


def test_resolve_config_path_direct_file(serotonin_cls, serotonin_config_path):
    resolved = serotonin_cls._resolve_config_path(str(serotonin_config_path))
    assert resolved == serotonin_config_path


def test_resolve_config_path_prefers_env_dir(monkeypatch, serotonin_cls, tmp_path: Path):
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    alt_cfg = env_dir / "serotonin.yaml"
    alt_cfg.write_text((
        Path(__file__).resolve().parents[4]
        / "configs"
        / "serotonin.yaml"
    ).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("TRADEPULSE_CONFIG_DIR", str(env_dir))

    resolved = serotonin_cls._resolve_config_path("nonexistent.yaml")

    assert resolved == alt_cfg


def test_resolve_config_path_missing(monkeypatch, serotonin_cls, tmp_path: Path):
    monkeypatch.delenv("TRADEPULSE_CONFIG_DIR", raising=False)
    with pytest.raises(FileNotFoundError):
        serotonin_cls._resolve_config_path(str(tmp_path / "missing.yaml"))


def test_estimate_aversive_state_matches_formula(serotonin_controller):
    ctrl = serotonin_controller
    cfg = ctrl.config
    market_vol = 4.0
    free_energy = 0.5
    losses = 0.8
    rho = 0.1

    result = ctrl.estimate_aversive_state(market_vol, free_energy, losses, rho)

    expected_release = (
        cfg["alpha"] * math.sqrt(market_vol)
        + cfg["beta"] * free_energy
        + cfg["gamma"] * (losses + 0.5 * losses ** 2)
        + cfg["delta_rho"] * (1.0 - rho)
    )
    expected = 3.0 * math.tanh(expected_release / 3.0)

    assert math.isclose(result, expected, rel_tol=1e-6)


def test_estimate_aversive_state_with_override_weights(serotonin_controller):
    ctrl = serotonin_controller
    overrides = {"alpha": ctrl.config["alpha"] * 2}

    baseline = ctrl.estimate_aversive_state(1.0, 0.5, 0.5, 0.0)
    overridden = ctrl.estimate_aversive_state(1.0, 0.5, 0.5, 0.0, overrides)

    assert overridden > baseline


def test_estimate_aversive_state_rejects_negative_inputs(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(-0.1, 0.2, 0.3, 0.0)
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(0.1, -0.2, 0.3, 0.0)
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(0.1, 0.2, -0.3, 0.0)


def test_compute_serotonin_signal_updates_floor(serotonin_controller):
    ctrl = serotonin_controller
    cfg = ctrl.config

    low = ctrl.compute_serotonin_signal(0.1)
    floor_low = ctrl.temperature_floor

    high = ctrl.compute_serotonin_signal(2.5)
    floor_high = ctrl.temperature_floor

    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert floor_low >= cfg["temperature_floor_min"]
    assert floor_high <= cfg["temperature_floor_max"]
    assert floor_high >= floor_low


def test_compute_serotonin_signal_rejects_negative(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.compute_serotonin_signal(-0.5)


def test_modulate_action_prob_applies_inhibition(serotonin_controller):
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.6
    result = ctrl.modulate_action_prob(0.8)

    cfg = ctrl.config
    inhibition_strength = ctrl.serotonin_level ** 2
    inhibition_factor = 1.0 - inhibition_strength * cfg["delta"]
    inhibited = 0.8 * max(0.0, inhibition_factor)
    bias_factor = 1.0 + cfg["za_bias"] * (1.0 - math.exp(-2.0 * ctrl.serotonin_level))
    expected = float(np.clip(inhibited * bias_factor, 0.0, 1.0))

    assert math.isclose(result, expected, rel_tol=1e-6)


def test_modulate_action_prob_rejects_invalid_probability(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.modulate_action_prob(1.5)


def test_apply_internal_shift_tempering(serotonin_controller):
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.7
    baseline = ctrl.apply_internal_shift(1.0, serotonin_signal=0.2)
    tempered = ctrl.apply_internal_shift(1.0, serotonin_signal=0.7)

    assert tempered < baseline
    assert tempered >= 0.0


def test_apply_internal_shift_requires_non_negative_gradient(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.apply_internal_shift(-0.1)


def test_check_cooldown_hysteresis(serotonin_controller):
    ctrl = serotonin_controller
    margin = 0.05
    threshold = ctrl.config["cooldown_threshold"]
    ctrl.phasic_level = 0.0
    ctrl.gate_level = 0.0

    ctrl._hold_state = False
    assert not ctrl.check_cooldown(threshold * (1.0 + margin) - 1e-6)
    assert ctrl.check_cooldown(threshold * (1.0 + margin) + 1e-6)

    ctrl._hold_state = True
    assert ctrl.check_cooldown(threshold * (1.0 - margin) + 1e-6)
    assert not ctrl.check_cooldown(threshold * (1.0 - margin) - 1e-6)


def test_check_cooldown_guard_can_block(monkeypatch, serotonin_controller):
    ctrl = serotonin_controller
    ctrl._hold_state = False
    ctrl.phasic_level = ctrl.config["phasic_veto"] * 2
    block_calls = []

    def guard(name: str, payload: dict) -> bool:
        block_calls.append((name, payload))
        return False

    ctrl.set_tacl_guard(guard)

    assert not ctrl.check_cooldown(ctrl.config["cooldown_threshold"] * 2)
    assert block_calls and block_calls[0][0] == "serotonin_cooldown"


def test_step_validates_inputs(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.step(stress=-0.1, drawdown=-0.01, novelty=0.2)
    with pytest.raises(ValueError):
        ctrl.step(stress=0.1, drawdown=0.01, novelty=0.2)
    with pytest.raises(ValueError):
        ctrl.step(stress=0.1, drawdown=-0.01, novelty=-0.2)


def test_step_returns_cooldown_tuple(monkeypatch, serotonin_module, serotonin_controller):
    ctrl = serotonin_controller
    times = [1000.0, 1000.1, 1000.2, 1000.3]

    def fake_time():
        return times.pop(0)

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    hold, veto, cooldown, level = ctrl.step(stress=0.2, drawdown=-0.01, novelty=0.2)

    assert hold in {True, False}
    assert veto in {True, False}
    assert cooldown >= 0.0
    assert 0.0 <= level <= 1.0


def test_to_dict_reports_current_state(monkeypatch, serotonin_module, serotonin_controller, tmp_path: Path):
    ctrl = serotonin_controller
    ctrl._hold_state = True
    ctrl._cooldown_start_time = 50.0

    times = [60.0]

    def fake_time():
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    snapshot = ctrl.to_dict()

    assert snapshot["hold_state"] is True
    assert snapshot["cooldown_s"] >= 10.0
    assert snapshot["temperature_floor"] >= ctrl.config["temperature_floor_min"]


def test_save_state_persists_json(monkeypatch, serotonin_module, serotonin_controller, tmp_path: Path):
    ctrl = serotonin_controller
    target = tmp_path / "state.json"

    times = [100.0, 100.0]

    def fake_time():
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    ctrl.save_state(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["_metadata"]["config_path"] == ctrl.config_path
    assert "serotonin_level" in data
