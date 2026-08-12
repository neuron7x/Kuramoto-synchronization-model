# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""meta_adapt must never drift a parameter out of its declared contract range.

meta_adapt multiplies config parameters by per-state factors (e.g. learning_rate_v
*= 1.01 on a 'good' regime). Applied repeatedly with no re-projection, a parameter
walks geometrically past its bound — learning_rate_v exceeds 1.0 — and, because
meta_adapt persists the config, the drifted value is written to disk and then
rejected by _validate_core_params on the next load. The controller must clamp each
adapted parameter back onto its contract so the persisted config always reloads.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from geosync.core.neuro.dopamine.dopamine_controller import DopamineController

_BASE_CONFIG = Path(__file__).resolve().parents[4] / "config" / "dopamine.yaml"


def _controller(tmp_path: Path, **overrides: Any) -> DopamineController:
    with open(_BASE_CONFIG, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    cfg.update(overrides)
    path = tmp_path / "dopamine.yaml"
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle)
    return DopamineController(str(path))


# sharpe ≥ target_sharpe (1.0) and drawdown ≥ target_dd (-0.05) ⇒ "good" regime.
_GOOD = {"sharpe": 5.0, "drawdown": 0.0}


def test_repeated_good_regime_keeps_learning_rate_in_contract(tmp_path: Path) -> None:
    ctrl = _controller(tmp_path, learning_rate_v=0.99, meta_cooldown_ticks=0)
    for _ in range(50):
        ctrl.meta_adapt(_GOOD)
    lr = float(ctrl.config["learning_rate_v"])
    # Without the clamp, 0.99 * 1.01**50 ≈ 1.63 — well outside (0, 1].
    assert 0.0 < lr <= 1.0


def test_persisted_config_reloads_after_sustained_adaptation(tmp_path: Path) -> None:
    ctrl = _controller(tmp_path, learning_rate_v=0.99, delta_gain=0.99, meta_cooldown_ticks=0)
    for _ in range(50):
        ctrl.meta_adapt(_GOOD)
    # The failure mode: a drifted value persisted to disk makes the next load raise.
    # A clean reload is the end-to-end proof the contract held.
    reloaded = DopamineController(str(ctrl.config_path))
    assert 0.0 < float(reloaded.config["learning_rate_v"]) <= 1.0
    assert 0.0 <= float(reloaded.config["delta_gain"]) <= 1.0


def test_clamp_pins_at_the_upper_boundary(tmp_path: Path) -> None:
    ctrl = _controller(tmp_path, learning_rate_v=0.999, delta_gain=0.999, meta_cooldown_ticks=0)
    for _ in range(20):
        ctrl.meta_adapt(_GOOD)
    assert float(ctrl.config["learning_rate_v"]) == pytest.approx(1.0)
    assert float(ctrl.config["delta_gain"]) == pytest.approx(1.0)
