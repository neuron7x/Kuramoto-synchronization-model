from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController

V24_TEMPLATE = {
    "alpha": 0.5,
    "beta": 0.3,
    "gamma": 0.4,
    "delta_rho": 0.2,
    "k": 1.5,
    "theta": 0.0,
    "delta": 0.5,
    "za_bias": 0.0,
    "decay_rate": 0.01,
    "cooldown_threshold": 0.7,
    "desens_threshold_ticks": 3,
    "desens_rate": 0.05,
    "target_dd": 0.15,
    "target_sharpe": 1.5,
    "beta_temper": 0.5,
    "phase_threshold": 0.7,
    "phase_kappa": 2.0,
    "burst_factor": 0.35,
    "mod_t_max": 10.0,
    "mod_t_half": 5.0,
    "mod_k": 0.5,
    "max_desens_counter": 10,
    "desens_gain": 0.8,
    "gate_veto": 0.9,
    "phasic_veto": 1.0,
    "temperature_floor_min": 0.1,
    "temperature_floor_max": 0.6,
    "hysteresis_margin": 0.05,
}

LEGACY_TEMPLATE = {
    "tonic_beta": 0.35,
    "phasic_beta": 0.55,
    "stress_gain": 1.0,
    "drawdown_gain": 1.2,
    "novelty_gain": 0.6,
    "stress_threshold": 0.7,
    "release_threshold": 0.4,
    "hysteresis": 0.1,
    "cooldown_ticks": 3,
    "chronic_window": 6,
    "desensitization_rate": 0.05,
    "desensitization_decay": 0.05,
    "max_desensitization": 0.6,
    "floor_min": 0.1,
    "floor_max": 0.6,
    "floor_gain": 0.8,
    "cooldown_extension": 2,
}


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_default_profile_is_v24_when_missing_active_profile(tmp_path: Path):
    cfg_path = _write_yaml(
        tmp_path / "serotonin.yaml",
        {
            "serotonin_v24": V24_TEMPLATE,
        },
    )
    controller = SerotoninController(str(cfg_path))
    assert controller._active_profile == "v24"
    assert controller.config["temperature_floor_min"] == V24_TEMPLATE["temperature_floor_min"]


def test_explicit_legacy_profile_loads(tmp_path: Path):
    cfg_path = _write_yaml(
        tmp_path / "serotonin_legacy.yaml",
        {
            "active_profile": "legacy",
            "serotonin_legacy": LEGACY_TEMPLATE,
        },
    )
    controller = SerotoninController(str(cfg_path))
    assert controller._active_profile == "legacy"
    assert controller.config["floor_min"] == LEGACY_TEMPLATE["floor_min"]
    assert controller.config["floor_max"] == LEGACY_TEMPLATE["floor_max"]


def test_flat_legacy_keys_remain_compatible(tmp_path: Path, caplog):
    caplog.set_level(logging.WARNING)
    cfg_path = _write_yaml(tmp_path / "legacy_flat.yaml", dict(LEGACY_TEMPLATE))
    controller = SerotoninController(str(cfg_path))
    assert controller._active_profile == "legacy"
    assert any("legacy serotonin keys" in message for message in caplog.text.splitlines())
    assert controller.config["floor_min"] == LEGACY_TEMPLATE["floor_min"]
