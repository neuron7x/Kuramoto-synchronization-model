#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail-closed: every RTM requirement's mapped Tests must exercise its mapped modules.

First principle (a traceability link nobody verifies is false confidence, not traceability):
``docs/requirements/traceability_matrix.md`` claims that each requirement's *Tests* column
covers its *Core/Execution/Runtime modules* column. Until now no gate checked that claim — a
row could map perf tests that never import the accelerator it allegedly covers (NFR-002), or
observability tests that never import ``core/telemetry.py`` (NFR-001). The matrix read GREEN
while the links were fictional.

This gate parses the matrix and, for each requirement, asserts that the UNION of its mapped
test files collectively imports at least one of its mapped modules:

    module cell ``core/telemetry.py``   -> import prefix ``core.telemetry``
    module cell ``core/accelerators``   -> any import under ``core.accelerators``
    ``N/A``                             -> ignored

A requirement whose tests import NONE of its modules is a dangling traceability link -> RED,
unless listed in ``.github/rtm_traceability_allowlist.json`` with a reason (e.g. a module that
is exercised only through an integration harness that imports it indirectly).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RTM = ROOT / "docs" / "requirements" / "traceability_matrix.md"
ALLOWLIST = ROOT / ".github" / "rtm_traceability_allowlist.json"

_LINK = re.compile(r"\[`([^`]+)`\]\([^)]+\)")  # [`path`](href)


def _cell_paths(cell: str) -> list[str]:
    """Extract repo-relative paths from a markdown table cell."""
    if not cell or cell.strip() in {"N/A", "—", "-", ""}:
        return []
    return [m.group(1) for m in _LINK.finditer(cell)]


def _to_module_prefix(path: str) -> str | None:
    """core/telemetry.py -> core.telemetry ; core/accelerators -> core.accelerators."""
    p = path.strip().lstrip("./")
    if p.endswith(".py"):
        p = p[:-3]
    p = p.strip("/")
    if not p or p.endswith(".md"):
        return None
    return p.replace("/", ".")


def _imports_of(test_path: str) -> set[str]:
    f = ROOT / test_path
    if not f.exists():
        return set()
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.add(node.module)
                for a in node.names:  # `from core import telemetry`
                    mods.add(f"{node.module}.{a.name}")
    return mods


def _covers(module_prefix: str, imported: set[str]) -> bool:
    return any(m == module_prefix or m.startswith(module_prefix + ".") for m in imported)


def _rows() -> list[tuple[str, list[str], list[str]]]:
    out: list[tuple[str, list[str], list[str]]] = []
    for line in RTM.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        req = cells[0]
        if req in {"Requirement", "---"} or set(req) <= {"-", " "}:
            continue
        # columns: Requirement | Title | Core | Execution | Runtime | ... | Tests(last)
        module_cells = cells[2:5]
        tests_cell = cells[-1]
        modules = [mp for c in module_cells for p in _cell_paths(c) if (mp := _to_module_prefix(p))]
        tests = [p for p in _cell_paths(tests_cell) if p.endswith(".py")]
        if modules:
            out.append((req, modules, tests))
    return out


def main() -> int:
    allow: dict[str, str] = {}
    if ALLOWLIST.exists():
        allow = json.loads(ALLOWLIST.read_text()).get("allow", {})

    dangling: list[str] = []
    ok = 0
    for req, modules, tests in _rows():
        imported: set[str] = set()
        for t in tests:
            imported |= _imports_of(t)
        if any(_covers(mp, imported) for mp in modules):
            ok += 1
        elif req in allow:
            ok += 1
        else:
            dangling.append(
                f"{req}: none of {len(tests)} mapped test(s) import any of {modules}"
            )

    total = ok + len(dangling)
    if dangling:
        print(
            f"[-] RTM traceability gate RED: {len(dangling)} requirement(s) whose mapped tests "
            f"exercise NONE of their mapped modules (a fictional traceability link):",
            file=sys.stderr,
        )
        for d in dangling:
            print(f"    {d}", file=sys.stderr)
        print(
            "    Fix docs/requirements/traceability_matrix.md to map tests that actually import "
            "the modules, or allowlist with a reason in "
            ".github/rtm_traceability_allowlist.json.",
            file=sys.stderr,
        )
        return 1
    print(f"[+] RTM traceability gate GREEN: {ok}/{total} requirements have a real test↔module link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
