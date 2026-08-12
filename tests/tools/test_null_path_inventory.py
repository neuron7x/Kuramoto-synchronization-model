# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Task 01: null-path inventory fail-closed checker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_null_path_inventory", _ROOT / "tools" / "validation" / "check_null_path_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_c = _load()


def test_committed_inventory_is_consistent() -> None:
    assert _c.main([], root=_ROOT) == 0


def test_missing_generator_file_fails(tmp_path: Path) -> None:
    data = {
        "generators": [{"name": "g", "path": "nope/missing.py", "class": "IID"}],
        "claim_paths": [{"path": "tools/validation/null_adequacy.py", "adequacy": "STRUCTURE_AGNOSTIC_OK"}],
    }
    errors = _c.evaluate(data, _ROOT)
    assert any("missing file nope/missing.py" in e for e in errors)


def test_bad_class_fails() -> None:
    data = {
        "generators": [{"name": "g", "path": "tools/validation/null_adequacy.py", "class": "WORLD_CLASS"}],
        "claim_paths": [{"path": "tools/validation/null_adequacy.py", "adequacy": "STRUCTURE_AGNOSTIC_OK"}],
    }
    errors = _c.evaluate(data, _ROOT)
    assert any("bad class" in e for e in errors)
