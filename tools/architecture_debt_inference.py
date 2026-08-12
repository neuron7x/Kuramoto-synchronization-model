#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Architecture-debt inference for the repository.

Surfaces structural debt as a single machine-readable inference: each
debt class is measured deterministically from the tree, compared against
an explicit threshold, and assigned a severity. The point is not a score
— it is to make the debt *legible and addressable* rather than implicit.

Read-only, offline, deterministic. It classifies debt; it does not
repair it, and it never reports a measure it could not compute as zero
(a measure that fails resolves to UNKNOWN, not OK).

Severity ladder: HIGH > MEDIUM > LOW > INFO. A class is `over_threshold`
when its measured count exceeds `threshold`. ``by_design`` classes are
standing architectural choices, reported for visibility, never as debt.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

ROOT = Path(__file__).resolve().parents[1]

HIGH, MEDIUM, LOW, INFO = "HIGH", "MEDIUM", "LOW", "INFO"
UNKNOWN = "UNKNOWN"


#: Directory names that are never repository content for debt accounting.
#: ``.venv`` is the local virtualenv; ``.git`` holds VCS internals; nested
#: git worktrees / agent checkouts live under ``.claude/worktrees`` and are
#: *other branches'* working copies, not this tree's source. Counting them
#: double-counts the repository and makes the metric depend on which local
#: worktrees happen to exist — so the same commit reports different debt on
#: CI (no worktrees) than on a developer box mid-fan-out. Excluding them makes
#: the inference deterministic and location-independent.
_EXCLUDED_DIR_PARTS: frozenset[str] = frozenset({".venv", ".git"})


def _is_excluded(path: Path) -> bool:
    """True if ``path`` lies in a non-source tree (venv, git, nested worktree)."""
    parts = path.parts
    if any(part in _EXCLUDED_DIR_PARTS for part in parts):
        return True
    # ``.claude/worktrees/<name>/...`` — a nested checkout of another branch.
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return True
    return False


def _py_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py") if not _is_excluded(p)]


def _grep_count(pattern: str) -> int:
    rx = re.compile(pattern)
    n = 0
    for f in _py_files():
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        n += len(rx.findall(text))
    return n


def _acceptor_files() -> list[Path]:
    base = ROOT / ".claude" / "commit_acceptors"
    return sorted(base.glob("*.yaml")) if base.exists() else []


def m_empty_evidence_ledger() -> tuple[int, int]:
    """Acceptors whose inline evidence ledger is empty (`evidence: []`).

    Returns (empty, total). Per the populated-evidence-ledger invariant,
    an empty inline ledger is unbacked governance.
    """
    files = _acceptor_files()
    empty = sum(1 for f in files if re.search(r"^evidence:\s*\[\]\s*$", f.read_text(), re.M))
    return empty, len(files)


def m_type_ignore() -> int:
    # Comment-form only — an inline `type: ignore` suppression, not the phrase in
    # a docstring or string literal (this module must not match its own example).
    return _grep_count(r"#\s*type:\s*ignore")


def m_noqa() -> int:
    return _grep_count(r"\bnoqa\b")


# A skip whose reason matches one of these is an environment/availability
# gate (optional dependency, absent fixture/data, platform capability) —
# the test runs wherever the precondition holds, so it is NOT actionable
# debt. Empirically validated: with hypothesis/z3/PyWavelets installed,
# every dep-gated property/formal/fuzz test passes.
_CONDITIONAL_SKIP = re.compile(
    r"not installed|not available|dependency is not|is not installed|"
    r"required for|requires |absent|not present|not on PATH|not supported|"
    r"not importable|fixtures unavailable|file not found|not staged|"
    r"not yet committed|getter path unavailable|EXCHANGE_CANARY|SSL|"
    r"only when|nothing to compare",
    re.IGNORECASE,
)

_SKIP_LINE = re.compile(
    r"pytest\.(?:mark\.)?skip(?:if)?\([^)]*?" r"(?:reason\s*=\s*)?[\"']([^\"']+)[\"']"
)


def m_test_skips() -> int:
    """Count *actionable* skips only — skips whose reason is not an
    environment/availability gate. Marker-counting overcounts; a skip
    that fires only when an optional dep or data fixture is absent is
    conditional coverage, not debt."""
    tests = ROOT / "tests"
    if not tests.exists():
        return 0
    actionable = 0
    for f in tests.rglob("*.py"):
        if _is_excluded(f):
            continue
        for reason in _SKIP_LINE.findall(f.read_text(encoding="utf-8")):
            if not _CONDITIONAL_SKIP.search(reason):
                actionable += 1
    return actionable


def m_test_slow() -> int:
    rx = re.compile(r"pytest\.mark\.slow\b")
    return sum(
        1
        for f in (ROOT / "tests").rglob("*.py")
        if (ROOT / "tests").exists()
        and not _is_excluded(f)
        and rx.search(f.read_text(encoding="utf-8"))
    )


def m_todo_markers() -> int:
    return _grep_count(r"\b(TODO|FIXME|HACK|XXX)\b")


def m_dual_physics_layers() -> int:
    a = ROOT / ".claude" / "physics"
    b = ROOT / "physics_contracts"
    return int(a.exists() and b.exists())


@dataclass(frozen=True)
class DebtClass:
    id: str
    title: str
    severity: str
    threshold: int
    measure: Callable[[], int]
    note: str
    by_design: bool = False
    # Hard-ratcheted only when the class is genuinely monotonic-reducible.
    # empty_evidence_ledger grows by construction with every new acceptor
    # (new acceptors default to evidence: []), so ratcheting it would
    # punish every PR that adds an acceptor — it is tracked, not gated.
    ratchet: bool = True


# The catalogue. Thresholds are explicit budgets; exceeding them flags debt.
CLASSES: tuple[DebtClass, ...] = (
    DebtClass(
        "empty_evidence_ledger",
        "Commit-acceptors with an empty inline evidence ledger",
        HIGH,
        threshold=0,
        measure=lambda: m_empty_evidence_ledger()[0],
        note="evidence: [] is schema-VALID (the field is optional and the "
        "validator only warns). Flagged as a policy gap, not a schema "
        "violation: the populated-evidence-ledger operating invariant expects "
        "materialized proof, and these acceptors defer it. Tracked, not "
        "ratcheted — it grows with every new acceptor by construction.",
        ratchet=False,
    ),
    DebtClass(
        "type_ignore_suppressions",
        "`type: ignore` suppressions across the Python surface",
        MEDIUM,
        threshold=400,
        measure=m_type_ignore,
        note="Each suppression is a hole in the --strict type contract; "
        "concentrated in tests but not exclusively.",
    ),
    DebtClass(
        "noqa_suppressions",
        "`noqa` lint suppressions across the Python surface",
        LOW,
        threshold=400,
        measure=m_noqa,
        note="Lint exceptions; track the trend, do not let it grow silently.",
    ),
    DebtClass(
        "actionable_test_skips",
        "Skips whose reason is not an environment/availability gate",
        MEDIUM,
        threshold=10,
        measure=m_test_skips,
        note="Excludes optional-dependency, absent-fixture, and platform "
        "gates (those run wherever the precondition holds). Only skips that "
        "represent genuinely deferred coverage are counted.",
    ),
    DebtClass(
        "test_slow_files",
        "Test files marked slow (excluded from fast lanes)",
        LOW,
        threshold=40,
        measure=m_test_slow,
        note="Slow-marked tests do not run in the fast gate; drift hides here.",
    ),
    DebtClass(
        "todo_markers",
        "TODO/FIXME/HACK/XXX markers in Python",
        LOW,
        threshold=30,
        measure=m_todo_markers,
        note="Inline deferrals; low count is healthy.",
    ),
    DebtClass(
        "dual_physics_contract_layers",
        "Parallel physics-contract layers (.claude/physics + physics_contracts)",
        INFO,
        threshold=1,
        measure=m_dual_physics_layers,
        note="Sanctioned duality (keep both); reported for visibility only.",
        by_design=True,
    ),
)


def infer() -> dict[str, object]:
    findings: list[dict[str, object]] = []
    worst = INFO
    order = {INFO: 0, LOW: 1, MEDIUM: 2, HIGH: 3, UNKNOWN: 4}
    for c in CLASSES:
        try:
            count = c.measure()
            status = UNKNOWN if count < 0 else ("DEBT" if count > c.threshold else "OK")
        except Exception:
            count, status = -1, UNKNOWN
        effective = (
            c.severity
            if (status == "DEBT" and not c.by_design)
            else (UNKNOWN if status == UNKNOWN else INFO)
        )
        if order[effective] > order[worst]:
            worst = effective
        extra: dict[str, object] = {}
        if c.id == "empty_evidence_ledger":
            empty, total = m_empty_evidence_ledger()
            extra = {"total_acceptors": total, "ratio": round(empty / total, 3) if total else None}
        findings.append(
            {
                "id": c.id,
                "title": c.title,
                "severity": c.severity,
                "count": count,
                "threshold": c.threshold,
                "status": status,
                "by_design": c.by_design,
                "ratchet": c.ratchet,
                "note": c.note,
                **extra,
            }
        )
    return {
        "worst_severity": worst,
        "debt_classes": findings,
        "actionable": [f["id"] for f in findings if f["status"] == "DEBT" and not f["by_design"]],
    }


def load_budget(path: Path) -> dict[str, int]:
    """Load the per-class debt ceiling. Unknown keys are ignored; a class
    absent from the budget is treated as ceiling 0 (no new debt classes
    may appear unbudgeted)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("budget", data)
    return {k: int(v) for k, v in raw.items() if isinstance(v, int)}


def ratchet(result: dict[str, object], budget: dict[str, int]) -> list[dict[str, object]]:
    """Return one regression record per class whose count exceeds its
    budget ceiling. Empty list == debt did not grow (ratchet holds).
    ``by_design`` classes are exempt; UNKNOWN counts never regress."""
    regressions: list[dict[str, object]] = []
    for f in cast("list[dict[str, object]]", result["debt_classes"]):
        if f["by_design"] or not f.get("ratchet", True):
            continue
        count = cast(int, f["count"])
        if count < 0:  # UNKNOWN
            continue
        ceiling = budget.get(str(f["id"]), 0)
        if count > ceiling:
            regressions.append(
                {"id": f["id"], "count": count, "budget": ceiling, "over_by": count - ceiling}
            )
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any actionable HIGH debt class is over threshold",
    )
    parser.add_argument(
        "--check",
        metavar="BUDGET",
        help="fail-closed ratchet: exit non-zero if any class exceeds the "
        "per-class ceiling in the BUDGET json (debt may shrink, never grow)",
    )
    args = parser.parse_args(argv)
    result = infer()

    if args.check:
        budget = load_budget(Path(args.check))
        regressions = ratchet(result, budget)
        if args.json:
            print(json.dumps({"regressions": regressions}, indent=2, sort_keys=True))
        else:
            if not regressions:
                print("debt ratchet: OK (no class grew past its budget)")
            for r in regressions:
                print(
                    f"REGRESSION {r['id']}: {r['count']} > budget {r['budget']} "
                    f"(+{r['over_by']}) — reduce the debt or lower nothing; "
                    f"the budget only moves down"
                )
        return 1 if regressions else 0
    classes = cast("list[dict[str, object]]", result["debt_classes"])
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for f in classes:
            flag = "·" if f["status"] == "OK" else f["status"]
            print(f"[{f['severity']:<6}] {flag:<7} {f['count']:>5} (>{f['threshold']}) {f['id']}")
        print(f"worst_severity: {result['worst_severity']}")
        actionable = cast("list[str]", result["actionable"])
        print(f"actionable: {', '.join(actionable) or 'none'}")
    has_high = any(
        f["status"] == "DEBT" and f["severity"] == HIGH and not f["by_design"] for f in classes
    )
    return 1 if args.strict and has_high else 0


if __name__ == "__main__":
    raise SystemExit(main())
