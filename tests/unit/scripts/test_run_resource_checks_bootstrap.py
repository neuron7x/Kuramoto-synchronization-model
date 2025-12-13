# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Regression tests for run_resource_checks bootstrap logic."""

from __future__ import annotations

import sys
from importlib import machinery, util
from pathlib import Path


def test_run_resource_checks_bootstrap_adds_src(monkeypatch) -> None:
    """Script should bootstrap src-layout so tradepulse imports resolve."""
    module_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "performance"
        / "run_resource_checks.py"
    )
    spec = util.spec_from_file_location("run_resource_checks_test", module_path)
    assert spec and spec.loader

    original_sys_path = sys.path.copy()
    try:
        base_paths = [p for p in original_sys_path if "TradePulse" not in p]
        sys.path[:] = base_paths  # simulate missing repo paths but keep stdlib
        monkeypatch.setenv("TP_SKIP_RESOURCE_IMPORTS", "1")
        module = util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        bootstrapped = sys.path.copy()
    finally:
        sys.path[:] = original_sys_path

    root = Path(__file__).resolve().parents[3]
    assert str(root / "src") in bootstrapped
    assert str(root) in bootstrapped
    assert machinery.PathFinder.find_spec("tradepulse", bootstrapped) is not None
