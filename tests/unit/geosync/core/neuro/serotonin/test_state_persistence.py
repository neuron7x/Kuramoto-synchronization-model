# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""State persistence coverage for the serotonin controller."""

from pathlib import Path

import pytest
import yaml


def _build_config(tmp_path: Path) -> Path:
    config = {
        "tonic_beta": 0.2,
        "phasic_beta": 0.4,
        "stress_gain": 1.0,
        "drawdown_gain": 1.1,
        "novelty_gain": 0.7,
        "stress_threshold": 0.75,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 4,
        "chronic_window": 5,
        "desensitization_rate": 0.04,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.6,
        "floor_min": 0.1,
        "floor_max": 0.7,
        "floor_gain": 0.9,
        "cooldown_extension": 2,
    }
    path = tmp_path / "serotonin.yaml"
    path.write_text(
        yaml.dump({"active_profile": "legacy", "serotonin_legacy": config}),
        encoding="utf-8",
    )
    return path


def _create_controller(tmp_path: Path):
    # Use proper package import instead of dynamic file loading
    # This ensures relative imports work correctly
    from geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController,
    )

    cfg_path = _build_config(tmp_path)
    ctrl = SerotoninController(str(cfg_path))
    cfg_path.unlink(missing_ok=True)
    return ctrl


def test_state_round_trip(tmp_path: Path):
    ctrl = _create_controller(tmp_path)
    for _ in range(10):
        ctrl.step(0.6, 0.2, 0.1)

    snapshot = ctrl.to_dict()
    path = tmp_path / "state.json"
    ctrl.save_state(str(path))

    ctrl.reset()
    assert ctrl.serotonin_level == 0

    ctrl.load_state(str(path))
    restored = ctrl.to_dict()

    assert restored["serotonin_level"] == pytest.approx(snapshot["serotonin_level"])
    assert restored["tonic_level"] == pytest.approx(snapshot["tonic_level"])
    assert restored["phasic_level"] == pytest.approx(snapshot["phasic_level"])
    assert bool(restored["hold_state"]) == bool(snapshot["hold_state"])
    assert restored["cooldown"] == pytest.approx(snapshot["cooldown"])
    assert restored["temperature_floor"] == pytest.approx(snapshot["temperature_floor"])
    assert restored["desens_counter"] == snapshot["desens_counter"]


def test_load_state_missing_file(tmp_path: Path):
    ctrl = _create_controller(tmp_path)
    path = tmp_path / "missing_state.json"

    with pytest.raises(FileNotFoundError):
        ctrl.load_state(str(path))
