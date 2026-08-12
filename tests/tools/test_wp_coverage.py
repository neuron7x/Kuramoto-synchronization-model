# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the Inference-Legend work-package coverage gate.

The live invariant ``test_committed_ledger_is_consistent`` proves the shipped
``docs/INFERENCE_LEGEND_WP_COVERAGE.md`` cites only artifacts that exist; the
synthetic cases prove the gate fails closed on each drift class (a vanished
artifact, a gap-with-code, a missing or mis-statused package).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "tools" / "inference" / "check_wp_coverage.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_wp_coverage", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_wp = _load()


def _all_ids_gap() -> list[dict[str, Any]]:
    return [
        {"id": f"WP-{i:02d}", "title": "t", "status": "GAP", "artifacts": []}
        for i in range(1, 11)
    ]


def test_committed_ledger_is_consistent() -> None:
    assert _wp.main([], root=_ROOT) == 0


def test_missing_artifact_fails(tmp_path: Path) -> None:
    pkgs = _all_ids_gap()
    pkgs[0] = {
        "id": "WP-01",
        "title": "t",
        "status": "EXISTS",
        "artifacts": ["core/definitely_not_here.py"],
    }
    result = _wp.evaluate({"work_packages": pkgs}, tmp_path)
    assert any("does not exist" in e for e in result.errors)


def test_gap_with_code_fails(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")
    pkgs = _all_ids_gap()
    pkgs[9] = {"id": "WP-10", "title": "t", "status": "GAP", "artifacts": ["real.py"]}
    result = _wp.evaluate({"work_packages": pkgs}, tmp_path)
    assert any("GAP must list no" in e for e in result.errors)


def test_missing_package_id_fails(tmp_path: Path) -> None:
    pkgs = _all_ids_gap()[:-1]  # drop WP-10
    result = _wp.evaluate({"work_packages": pkgs}, tmp_path)
    assert any("missing work-package ids" in e and "WP-10" in e for e in result.errors)


def test_unknown_status_fails(tmp_path: Path) -> None:
    pkgs = _all_ids_gap()
    pkgs[0]["status"] = "MAYBE"
    result = _wp.evaluate({"work_packages": pkgs}, tmp_path)
    assert any("not in" in e for e in result.errors)


def test_clean_synthetic_ledger_passes(tmp_path: Path) -> None:
    result = _wp.evaluate({"work_packages": _all_ids_gap()}, tmp_path)
    assert result.errors == []
