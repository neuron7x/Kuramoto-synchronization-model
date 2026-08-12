# SPDX-License-Identifier: MIT
"""Contract tests for the architecture-debt inference.

Pin the fail-closed semantics: a measure that cannot be computed is
UNKNOWN (never silently OK), by-design classes never count as actionable
debt, and the inference is deterministic and machine-readable.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "architecture_debt_inference.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("architecture_debt_inference", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_api() -> None:
    m = _load()
    assert callable(m.infer)
    assert callable(m.main)
    assert m.CLASSES


def test_infer_shape() -> None:
    m = _load()
    r = m.infer()
    assert set(r) == {"worst_severity", "debt_classes", "actionable"}
    assert r["worst_severity"] in {m.HIGH, m.MEDIUM, m.LOW, m.INFO, m.UNKNOWN}
    for f in r["debt_classes"]:
        assert {"id", "title", "severity", "count", "threshold", "status",
                "by_design", "note"} <= set(f)
        assert f["status"] in {"OK", "DEBT", m.UNKNOWN}


def test_every_class_has_explicit_threshold_and_severity() -> None:
    m = _load()
    for c in m.CLASSES:
        assert c.severity in {m.HIGH, m.MEDIUM, m.LOW, m.INFO}
        assert isinstance(c.threshold, int)
        assert c.note.strip()


def test_by_design_never_actionable() -> None:
    m = _load()
    r = m.infer()
    by_design_ids = {c.id for c in m.CLASSES if c.by_design}
    assert by_design_ids
    assert not (set(r["actionable"]) & by_design_ids)


def test_evidence_ledger_class_reports_ratio() -> None:
    m = _load()
    r = m.infer()
    f = next(x for x in r["debt_classes"] if x["id"] == "empty_evidence_ledger")
    assert "total_acceptors" in f and "ratio" in f
    assert f["count"] >= 0
    if f["total_acceptors"]:
        assert 0.0 <= f["ratio"] <= 1.0


def test_failing_measure_is_unknown_not_ok() -> None:
    m = _load()

    def boom() -> int:
        raise RuntimeError("cannot measure")

    broken = m.DebtClass("boom", "boom", m.HIGH, 0, boom, "x")
    m.CLASSES = (*m.CLASSES, broken)
    try:
        r = m.infer()
        f = next(x for x in r["debt_classes"] if x["id"] == "boom")
        assert f["status"] == m.UNKNOWN
        assert "boom" not in r["actionable"]  # UNKNOWN is not actionable DEBT
    finally:
        m.CLASSES = tuple(c for c in m.CLASSES if c.id != "boom")


def test_negative_count_is_unknown() -> None:
    m = _load()
    broken = m.DebtClass("neg", "neg", m.LOW, 0, lambda: -1, "x")
    m.CLASSES = (*m.CLASSES, broken)
    try:
        r = m.infer()
        f = next(x for x in r["debt_classes"] if x["id"] == "neg")
        assert f["status"] == m.UNKNOWN
    finally:
        m.CLASSES = tuple(c for c in m.CLASSES if c.id != "neg")


def test_deterministic() -> None:
    m = _load()
    assert m.infer() == m.infer()


def test_main_json_runs(capsys) -> None:
    import json

    m = _load()
    rc = m.main(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert "debt_classes" in data
    assert rc in (0, 1)


# --- debt ratchet -------------------------------------------------------
def test_ratchet_holds_at_budget(tmp_path) -> None:
    import json

    m = _load()
    result = m.infer()
    budget = {c["id"]: c["count"] for c in result["debt_classes"]
              if not c["by_design"] and c["count"] >= 0}
    assert m.ratchet(result, budget) == []


def test_ratchet_flags_growth() -> None:
    m = _load()
    result = m.infer()
    over = {c["id"]: 0 for c in result["debt_classes"]
            if not c["by_design"] and c["count"] > 0}
    regressions = m.ratchet(result, over)
    assert regressions
    assert all(r["over_by"] > 0 for r in regressions)


def test_ratchet_exempts_by_design_and_unknown() -> None:
    m = _load()
    result = m.infer()
    # by_design classes are never regressions even at budget 0
    zero = {c["id"]: 0 for c in result["debt_classes"]}
    flagged = {r["id"] for r in m.ratchet(result, zero)}
    by_design_ids = {c.id for c in m.CLASSES if c.by_design}
    assert not (flagged & by_design_ids)


def test_load_budget_reads_committed_file() -> None:
    from pathlib import Path

    m = _load()
    budget = m.load_budget(ROOT / "tools" / "debt_budget.json")
    assert budget["type_ignore_suppressions"] > 0
    assert isinstance(budget, dict)


def test_committed_budget_holds_on_current_tree() -> None:
    m = _load()
    budget = m.load_budget(ROOT / "tools" / "debt_budget.json")
    assert m.ratchet(m.infer(), budget) == [], (
        "debt grew past the committed budget — reduce it or lower the budget"
    )


def test_check_mode_exit_codes(tmp_path, capsys) -> None:
    import json

    m = _load()
    ok_budget = tmp_path / "ok.json"
    counts = {c["id"]: c["count"] for c in m.infer()["debt_classes"]}
    ok_budget.write_text(json.dumps({"budget": counts}))
    assert m.main(["--check", str(ok_budget)]) == 0
    capsys.readouterr()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"budget": {"todo_markers": 0}}))
    assert m.main(["--check", str(bad)]) == 1


def test_py_files_exclude_nested_worktrees_and_venv() -> None:
    # The metric must be location-independent: nested git worktrees / agent
    # checkouts under .claude/worktrees, the local .venv, and .git internals
    # are not this tree's source and must never be counted.
    m = _load()
    for p in m._py_files():
        parts = p.parts
        assert ".venv" not in parts
        assert ".git" not in parts
        assert not any(
            parts[i] == ".claude" and parts[i + 1] == "worktrees"
            for i in range(len(parts) - 1)
        ), f"nested worktree leaked into debt scan: {p}"


def test_is_excluded_predicate() -> None:
    m = _load()
    base = m.ROOT
    assert m._is_excluded(base / ".claude" / "worktrees" / "agent-x" / "core" / "a.py")
    assert m._is_excluded(base / ".venv" / "lib" / "x.py")
    assert m._is_excluded(base / ".git" / "hooks" / "x.py")
    assert not m._is_excluded(base / "core" / "physics" / "forman_ricci.py")
    # a legitimate source file that merely mentions the word elsewhere in path
    assert not m._is_excluded(base / "core" / "claude_adapter.py")


def test_evidence_ledger_is_tracked_not_ratcheted() -> None:
    # empty_evidence_ledger grows with every new acceptor by construction;
    # it must be reported but never hard-gated by the ratchet.
    m = _load()
    result = m.infer()
    f = next(x for x in result["debt_classes"] if x["id"] == "empty_evidence_ledger")
    assert f["ratchet"] is False
    # even with a budget of 0, it is not a regression
    assert not any(r["id"] == "empty_evidence_ledger"
                   for r in m.ratchet(result, {"empty_evidence_ledger": 0}))
