from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tradepulse.core.neuro.dopamine.ddm_adapter import ddm_thresholds


CONFIG = yaml.safe_load(Path("config/dopamine.yaml").read_text(encoding="utf-8"))


def _kwargs() -> dict[str, float]:
    return {
        "temp_gain": float(CONFIG["ddm_temp_gain"]),
        "threshold_gain": float(CONFIG["ddm_threshold_gain"]),
        "hold_gain": float(CONFIG["ddm_hold_gain"]),
        "min_temp_scale": float(CONFIG["ddm_min_temperature_scale"]),
        "max_temp_scale": float(CONFIG["ddm_max_temperature_scale"]),
        "baseline_a": float(CONFIG["ddm_baseline_a"]),
        "baseline_t0": float(CONFIG["ddm_baseline_t0"]),
        "eps": float(CONFIG["ddm_eps"]),
    }


def test_thresholds_respect_monotonicity() -> None:
    fast = ddm_thresholds(1.5, CONFIG["ddm_baseline_a"], CONFIG["ddm_baseline_t0"], **_kwargs())
    slow = ddm_thresholds(0.2, CONFIG["ddm_baseline_a"], CONFIG["ddm_baseline_t0"], **_kwargs())
    delayed = ddm_thresholds(
        0.2,
        CONFIG["ddm_baseline_a"],
        CONFIG["ddm_baseline_t0"] + 0.3,
        **_kwargs(),
    )

    assert fast.temperature_scale <= slow.temperature_scale
    assert delayed.hold_threshold >= slow.hold_threshold
    assert fast.go_threshold >= fast.no_go_threshold


def test_threshold_validation() -> None:
    with pytest.raises(ValueError):
        ddm_thresholds(float("nan"), 1.0, 0.2, **_kwargs())
    with pytest.raises(ValueError):
        ddm_thresholds(0.5, -0.1, 0.2, **_kwargs())
