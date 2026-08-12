# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the falsifier.test_id resolution gate.

Keystone: ``test_real_tree_all_falsifiers_resolve`` locks the current good
state (every CLAIMS.yaml falsifier points at a live test); the synthetic cases
prove the gate FAILS on a rotted pointer (missing file / missing function), so
the lock is real, not vacuous.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_falsifier_test_ids_resolve",
        _ROOT / "tools" / "claims" / "check_falsifier_test_ids_resolve.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_m = _load()


def test_real_tree_all_falsifiers_resolve() -> None:
    """Regression guard: every committed falsifier.test_id resolves today."""
    assert _m.main([]) == 0


def test_missing_file_is_rot() -> None:
    err = _m.resolve_node_id("tests/does/not/exist_test.py::test_x", _ROOT)
    assert err is not None and "file does not exist" in err


def test_missing_function_is_rot(tmp_path: Path) -> None:
    f = tmp_path / "test_sample.py"
    f.write_text("def test_present():\n    pass\n", encoding="utf-8")
    assert _m.resolve_node_id("test_sample.py::test_absent", tmp_path) is not None
    assert _m.resolve_node_id("test_sample.py::test_present", tmp_path) is None


def test_parametrised_suffix_stripped(tmp_path: Path) -> None:
    f = tmp_path / "test_p.py"
    f.write_text("def test_axis():\n    pass\n", encoding="utf-8")
    assert _m.resolve_node_id("test_p.py::test_axis[case-3]", tmp_path) is None


def test_class_method_resolution(tmp_path: Path) -> None:
    f = tmp_path / "test_c.py"
    f.write_text("class TestThing:\n    def test_method(self):\n        pass\n", encoding="utf-8")
    assert _m.resolve_node_id("test_c.py::TestThing::test_method", tmp_path) is None
    assert _m.resolve_node_id("test_c.py::TestThing::test_gone", tmp_path) is not None


def test_not_a_node_id() -> None:
    assert _m.resolve_node_id("tests/foo.py", _ROOT) is not None


def test_check_collects_rot(tmp_path: Path) -> None:
    claims = tmp_path / "CLAIMS.yaml"
    claims.write_text(
        "claims:\n"
        "  - id: good\n"
        "    falsifier:\n"
        "      test_id: t.py::test_ok\n"
        "  - id: bad\n"
        "    falsifier:\n"
        "      test_id: t.py::test_missing\n",
        encoding="utf-8",
    )
    (tmp_path / "t.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    errors = _m.check(claims, root=tmp_path)
    assert len(errors) == 1 and "[bad]" in errors[0]
