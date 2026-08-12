# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regressions for the physics test validator (.claude/physics).

Two fail-open defects (DEFECT 2):
  * a physics test that fails ``ast.parse`` yields an L0 issue, but the exit-code
    total summed only L1..L5 — so a syntactically broken (unrunnable) physics
    test scored as "All physics tests pass" with exit 0.
  * an empty/unloadable INVARIANTS.yaml only printed a WARNING and continued
    exit 0, silently disabling L2/L3 grounding while ``_self_check`` fail-closes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_MOD_PATH = Path(__file__).resolve().parents[2] / ".claude" / "physics" / "validate_tests.py"
_spec = importlib.util.spec_from_file_location("validate_tests_under_test", _MOD_PATH)
assert _spec and _spec.loader
vt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vt)


def test_unparseable_physics_test_yields_L0() -> None:
    # The pure function: a syntax error must surface as an L0 issue, not silence.
    tmp = Path(__file__).resolve().parent
    broken = tmp / "_tmp_broken_kuramoto_probe.py"
    broken.write_text("def test_kuramoto(:\n    pass\n", encoding="utf-8")
    try:
        issues = vt.check_test_file(broken, {})
    finally:
        broken.unlink(missing_ok=True)
    assert [i.level for i in issues] == ["L0"]


def test_run_validation_fails_closed_on_unparseable_test(tmp_path: Path) -> None:
    # DEFECT 2: an unparseable physics test must fail the gate (non-zero exit),
    # not be reported as "All physics tests pass validation" (exit 0).
    broken = tmp_path / "test_kuramoto_broken.py"
    broken.write_text("def test_kuramoto_sync(:\n    assert R < 1\n", encoding="utf-8")
    assert vt.is_physics_test(broken)  # filename routes it into the physics gate
    with pytest.raises(SystemExit) as exc:
        vt._run_test_validation([broken], {}, summary_mode=True)
    assert exc.value.code == 1


def test_main_fails_closed_when_registry_unloadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # DEFECT 2: an empty/unloadable INVARIANTS.yaml must fail closed (like
    # _self_check), never continue GREEN with L2/L3 checks silently disabled.
    def _empty() -> dict[str, Any]:
        return {}

    monkeypatch.setattr(vt, "load_invariants", _empty)
    monkeypatch.setattr(vt.sys, "argv", ["validate_tests", str(tmp_path / "any.py")])
    with pytest.raises(SystemExit) as exc:
        vt.main()
    assert exc.value.code == 1
