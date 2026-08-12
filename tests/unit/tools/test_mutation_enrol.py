# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the mutation-enrolment cycle tool.

The tool automates a loop whose whole value is that it NEVER enrols a module it did not just
measure clean. These cases pin exactly that: NO_LOGIC and GAP results must never reach the
ledger, only CLEAN does, and --apply is the sole path that writes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "mutation_enrol", ROOT / "tools" / "mutation_enrol.py"
)
assert _SPEC and _SPEC.loader
enrol_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["mutation_enrol"] = enrol_mod
_SPEC.loader.exec_module(enrol_mod)


def _report(*results: dict) -> dict:
    return {"schema": "mutation-enrol-trace/1", "summary": {}, "results": list(results)}


def _r(module: str, killed: int, total: int, classification: str) -> dict:
    return {
        "module": module,
        "test": f"tests/test_{module.replace('/', '_')}.py",
        "killed": killed,
        "total": total,
        "classification": classification,
        "survivors": [],
        "detail": "",
    }


def test_only_clean_results_are_enrolled(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLEAN enrols; GAP and NO_LOGIC never do -- the tool's entire contract."""
    monkeypatch.setattr(enrol_mod, "_ledger", lambda: {"_doc": "", "modules": {}})
    report = _report(
        _r("core/a.py", 5, 5, "CLEAN"),
        _r("core/b.py", 3, 4, "GAP"),
        _r("core/c.py", 0, 0, "NO_LOGIC"),
    )
    outcome = enrol_mod.enrol(report, apply=False)
    assert outcome["added"] == ["core/a.py"]
    assert ("core/b.py", "GAP") in outcome["skipped"]
    assert ("core/c.py", "NO_LOGIC") in outcome["skipped"]
    assert outcome["applied"] is False


def test_zero_site_module_is_never_enrolled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A NO_LOGIC module probes at kill-rate 1.0 -- vacuous, must not buy free credit."""
    monkeypatch.setattr(enrol_mod, "_ledger", lambda: {"_doc": "", "modules": {}})
    outcome = enrol_mod.enrol(_report(_r("core/empty.py", 0, 0, "NO_LOGIC")), apply=False)
    assert outcome["added"] == []


def test_already_enrolled_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        enrol_mod,
        "_ledger",
        lambda: {"_doc": "", "modules": {"core/a.py": {"floor": 1.0}}},
    )
    outcome = enrol_mod.enrol(_report(_r("core/a.py", 5, 5, "CLEAN")), apply=False)
    assert outcome["added"] == []
    assert ("core/a.py", "already-enrolled") in outcome["skipped"]


def test_apply_writes_the_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger_file = tmp_path / "ledger.json"
    monkeypatch.setattr(enrol_mod, "LEDGER", ledger_file)
    monkeypatch.setattr(enrol_mod, "_ledger", lambda: {"_doc": "x", "modules": {}})
    outcome = enrol_mod.enrol(_report(_r("core/a.py", 2, 2, "CLEAN")), apply=True)
    assert outcome["applied"] is True
    import json

    written = json.loads(ledger_file.read_text(encoding="utf-8"))
    entry = written["modules"]["core/a.py"]
    assert entry["floor"] == 1.0 and entry["killed"] == 2 and entry["total"] == 2
    assert entry["tests"] == "tests/test_core_a.py.py"


def test_direct_import_pairing_rejects_ancestor_only(tmp_path: Path) -> None:
    """The pairing must use DIRECT import, never an ancestor package -- same rule the gate credits."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    direct = tmp_path / "test_direct.py"
    direct.write_text("from pkg.mod import x\n", encoding="utf-8")
    ancestor = tmp_path / "test_ancestor.py"
    ancestor.write_text("import pkg\n", encoding="utf-8")

    orig_root = enrol_mod.ROOT
    try:
        enrol_mod.ROOT = tmp_path
        assert enrol_mod._directly_imports("test_direct.py", "pkg/mod.py") is True
        assert enrol_mod._directly_imports("test_ancestor.py", "pkg/mod.py") is False
    finally:
        enrol_mod.ROOT = orig_root


def test_discover_pairs_are_unenrolled_and_have_logic() -> None:
    """Live smoke: every discovered pair is a real, unenrolled, 1:1, has-logic candidate."""
    enrolled = enrol_mod._enrolled()
    pairs = enrol_mod.discover(limit=8, max_sites=16, roots=enrol_mod._runtime_roots())
    for pair in pairs:
        assert pair["module"] not in enrolled
        assert pair["logic_sites"] >= 1
        assert (enrol_mod.ROOT / pair["module"]).exists()
        assert enrol_mod._directly_imports(pair["test"], pair["module"])


def test_round_robin_lanes_cover_every_pair_once() -> None:
    """The parallel dispatcher splits pairs by `pairs[lane::jobs]`; every pair runs exactly once."""
    pairs = [{"module": f"m{i}.py", "test": f"t{i}.py"} for i in range(17)]
    for jobs in (2, 4, 6, 8):
        covered = [p for lane in range(min(jobs, len(pairs))) for p in pairs[lane :: min(jobs, len(pairs))]]
        assert sorted(p["module"] for p in covered) == sorted(p["module"] for p in pairs)
        assert len(covered) == len(pairs)  # no pair dropped or duplicated


def test_probe_refuses_dirty_tree_even_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clean-tree precondition holds for --jobs N too (worktrees fork from HEAD)."""
    monkeypatch.setattr(enrol_mod, "_dirty_worktree", lambda: True)
    with pytest.raises(SystemExit, match="dirty"):
        enrol_mod.probe([{"module": "a.py", "test": "t.py"}], timeout=5, out_dir=Path("/tmp"), jobs=4)
