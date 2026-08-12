# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Task 16: OOS-split inventory regression guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_oos_split_inventory", _ROOT / "tools" / "validation" / "check_oos_split_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_c = _load()


def test_committed_inventory_is_consistent() -> None:
    assert _c.main([], root=_ROOT) == 0


def test_lost_marker_fails(tmp_path: Path) -> None:
    f = tmp_path / "split.py"
    f.write_text("def split(): pass\n", encoding="utf-8")  # no 'embargo' marker
    data = {"splits": [{"path": "split.py", "protection": "EMBARGO", "marker": "embargo"}]}
    errors = _c.evaluate(data, tmp_path)
    assert any("marker 'embargo' is GONE" in e for e in errors)


def test_missing_path_fails(tmp_path: Path) -> None:
    data = {"splits": [{"path": "nope.py", "protection": "EMBARGO", "marker": "embargo"}]}
    errors = _c.evaluate(data, tmp_path)
    assert any("split path missing" in e for e in errors)


def test_null_marker_needs_no_token(tmp_path: Path) -> None:
    f = tmp_path / "safe.py"
    f.write_text("x = 1\n", encoding="utf-8")
    data = {"splits": [{"path": "safe.py", "protection": "GLOBAL_AGGREGATE_NO_BOUNDARY_LEAK", "marker": None}]}
    assert _c.evaluate(data, tmp_path) == []
