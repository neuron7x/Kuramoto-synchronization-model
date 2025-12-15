"""State persistence coverage for the serotonin controller."""

import json
from pathlib import Path
from typing import Any

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
    from tradepulse.core.neuro.serotonin.serotonin_controller import (
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
    ctrl.save_state(path)

    ctrl.reset()
    assert ctrl.level == 0

    restored = ctrl.load_state(path)

    assert restored["level"] == pytest.approx(snapshot["level"])
    assert restored["tonic_level"] == pytest.approx(snapshot["tonic_level"])
    assert restored["phasic_level"] == pytest.approx(snapshot["phasic_level"])
    assert bool(restored["hold"]) == bool(snapshot["hold"])
    assert restored["cooldown"] == pytest.approx(snapshot["cooldown"])
    assert restored["temperature_floor"] == pytest.approx(snapshot["temperature_floor"])
    assert restored["desensitization"] == pytest.approx(snapshot["desensitization"])


def test_load_state_validation(tmp_path: Path):
    ctrl = _create_controller(tmp_path)
    bad_state: dict[str, Any] = {
        "tonic_level": 0.1,
        "phasic_level": 0.1,
        "level": 2.1,  # exceeds max
        "hold": False,
        "active_hold": False,
        "cooldown": 0,
        "temperature_floor": 0.2,
        "desensitization": 0.0,
    }

    path = tmp_path / "bad_state.json"
    path.write_text(json.dumps(bad_state), encoding="utf-8")

    with pytest.raises(ValueError):
        ctrl.load_state(path)
