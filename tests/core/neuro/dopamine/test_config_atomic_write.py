# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""save_config_to_yaml must be atomic: meta_adapt persists from the control loop,
so a crash or concurrent reader must never see a truncated config, and a failed
write must leave the previous config intact with no temp file left behind.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import geosync.core.neuro.dopamine.dopamine_controller as dopamine_mod
from geosync.core.neuro.dopamine.dopamine_controller import DopamineController

_BASE = Path(__file__).resolve().parents[4] / "config" / "dopamine.yaml"


def _controller(tmp_path: Path) -> DopamineController:
    with open(_BASE, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    path = tmp_path / "dopamine.yaml"
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle)
    return DopamineController(str(path))


def test_save_is_reloadable_and_leaves_no_temp(tmp_path: Path) -> None:
    ctrl = _controller(tmp_path)
    ctrl.config["learning_rate_v"] = 0.5
    ctrl.save_config_to_yaml()
    # The persisted config must load cleanly through the full validator.
    reloaded = DopamineController(str(ctrl.config_path))
    assert float(reloaded.config["learning_rate_v"]) == pytest.approx(0.5)
    assert list(tmp_path.glob(".dopamine-*")) == []


def test_failed_write_does_not_corrupt_the_previous_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctrl = _controller(tmp_path)
    original = Path(ctrl.config_path).read_text(encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated disk failure mid-write")

    monkeypatch.setattr(dopamine_mod.yaml, "safe_dump", boom)
    with pytest.raises(RuntimeError):
        ctrl.save_config_to_yaml()

    # os.replace never ran, so the on-disk config is byte-for-byte the old one,
    # and the aborted temp file was cleaned up.
    assert Path(ctrl.config_path).read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".dopamine-*")) == []
