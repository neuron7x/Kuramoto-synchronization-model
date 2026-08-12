# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification suite for the attribute-existence gate.

The gate exists for one line: `getattr(kill_switch, "activate", None)`, where the module
exports `activate_kill_switch`. The lookup returned None, `callable(None)` was False, and
a CRITICAL security incident's emergency halt did nothing at all.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "ci" / "check_attribute_existence.py"


def _gate(root: Path):
    spec = importlib.util.spec_from_file_location("_attrexist", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_attrexist"] = mod
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = root
    mod.SCAN_ROOT = root / "geosync"
    return mod


def _tree(root: Path, target: str, caller: str) -> None:
    pkg = root / "geosync" / "runtime"
    pkg.mkdir(parents=True, exist_ok=True)
    for p in (root / "geosync", pkg):
        (p / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "kill_switch.py").write_text(target, encoding="utf-8")
    (pkg / "caller.py").write_text(caller, encoding="utf-8")


def test_the_live_tree_holds() -> None:
    proc = subprocess.run([sys.executable, str(GATE)], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_name_that_does_not_exist_is_caught(tmp_path: Path) -> None:
    """POSITIVE CONTROL: the exact defect — the halt that never fired."""
    _tree(tmp_path,
          "def activate_kill_switch(reason, source):\n    pass\n",
          "from geosync.runtime import kill_switch\n"
          "a = getattr(kill_switch, 'activate', None)\n")
    v = _gate(tmp_path).find_dangling_getattr()
    assert v and "activate" in v[0]


def test_a_name_that_exists_is_not_flagged(tmp_path: Path) -> None:
    _tree(tmp_path,
          "def activate_kill_switch(reason, source):\n    pass\n",
          "from geosync.runtime import kill_switch\n"
          "a = getattr(kill_switch, 'activate_kill_switch', None)\n")
    assert _gate(tmp_path).find_dangling_getattr() == []


def test_a_conditionally_bound_name_is_not_flagged(tmp_path: Path) -> None:
    """NEGATIVE CONTROL: an optional-dependency flag is a real binding.

    A first draft walked only the flat module body and cried wolf on `_DEAP_AVAILABLE`.
    A gate that flags correct code gets suppressed, and is then worth less than nothing.
    """
    _tree(tmp_path,
          "try:\n    import deap\nexcept ModuleNotFoundError:\n"
          "    _AVAILABLE = False\nelse:\n    _AVAILABLE = True\n",
          "from geosync.runtime import kill_switch\n"
          "a = getattr(kill_switch, '_AVAILABLE', None)\n")
    assert _gate(tmp_path).find_dangling_getattr() == []


def test_third_party_modules_are_out_of_scope(tmp_path: Path) -> None:
    """getattr(numpy, 'bfloat16', None) is feature-detection, not a bug.

    A missing name in a dependency is a VERSION, not a defect — that is what the default
    is for. We control geosync; we do not control numpy.
    """
    _tree(tmp_path, "x = 1\n",
          "import numpy\na = getattr(numpy, 'no_such_thing_at_all', None)\n")
    assert _gate(tmp_path).find_dangling_getattr() == []
