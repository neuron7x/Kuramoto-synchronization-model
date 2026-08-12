# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Research may exist; research may not masquerade as runtime truth.

``geosync_research`` is packaged but research-only. This gate quarantines it: it
may be absent from release coverage ONLY with reason ``research``, no production
package may import it, and no release artifact may count it as measured production
signal. If research enters the runtime import graph, CI fails.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "artifacts" / "coverage_surface" / "coverage_surface_report.json"
ALLOWLIST = ROOT / "tests" / "fixtures" / "coverage_surface_allowlist.json"
RESEARCH = "geosync_research"
_PRODUCTION_ROOTS = ("execution", "application", "interfaces", "core", "backtest")


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_research_absent_from_coverage_only_with_research_reason() -> None:
    report = _report()
    if RESEARCH not in report.get("missing_from_coverage", []):
        return  # measured — nothing to quarantine
    allowlisted = {e["root"]: e for e in report.get("allowlisted", [])}
    assert RESEARCH in allowlisted, "research is missing from coverage but not allowlisted"
    assert allowlisted[RESEARCH]["reason"] == "research", allowlisted[RESEARCH]


def test_allowlist_entry_reason_is_research() -> None:
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    if RESEARCH in allow:
        assert allow[RESEARCH]["reason"] == "research", allow[RESEARCH]


def test_research_never_counted_as_measured_production() -> None:
    report = _report()
    assert RESEARCH not in report.get("measured", []), "research must never be a measured root"


def test_no_production_package_imports_research() -> None:
    offenders: list[str] = []
    for root in _PRODUCTION_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == RESEARCH or alias.name.startswith(RESEARCH + "."):
                            offenders.append(f"{path.relative_to(ROOT)}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == RESEARCH or node.module.startswith(RESEARCH + "."):
                        offenders.append(f"{path.relative_to(ROOT)}: from {node.module}")
    assert not offenders, "production code imports research (runtime leak): " + "; ".join(offenders[:5])
