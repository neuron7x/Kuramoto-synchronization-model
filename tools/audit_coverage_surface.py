# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Audit the packaged production surface against the measured coverage surface.

Root problem this closes: a package can be shipped in the wheel
(``[tool.setuptools.packages.find].include``) yet appear in NO coverage
profile's ``source`` — a false denominator, since that code is installed but
never counted. This audit binds every packaged root to an explicit decision:

    measured    the root appears in at least one coverage profile's source
                (pyproject ``[tool.coverage.run].source`` OR any ``*.coveragerc``);
    allowlisted the root is declared non-runtime / tooling / deferred with a
                concrete reason in ``tests/fixtures/coverage_surface_allowlist.json``;
    forbidden   the root is neither — a silent shipped-but-uncounted gap.

``verdict == FAIL`` iff ``forbidden_gaps`` is non-empty. The gate is a ratchet:
a NEW packaged package that is neither measured nor allowlisted fails closed.

This does NOT modify or enforce any coverage percentage / ``fail_under`` — it
only audits the *declared* surface binding. Percentage enforcement stays with
the named critical (98) and release (90) profiles.

Usage:
    python tools/audit_coverage_surface.py \
        --out artifacts/coverage_surface/coverage_surface_report.json
"""

from __future__ import annotations

import argparse
import configparser
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
ALLOWLIST = REPO_ROOT / "tests" / "fixtures" / "coverage_surface_allowlist.json"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "coverage_surface" / "coverage_surface_report.json"

# Concrete allowlist categories. No vague reasons ("later", "optional",
# "low priority"). Every category names *why* a packaged root is not in a
# coverage denominator.
ALLOWED_REASONS: frozenset[str] = frozenset(
    {
        "research",  # research-only; not production runtime
        "sandbox",  # prototype-only; not release surface
        "generated",  # generated code; covered by generator contract
        "docs_only",  # non-runtime documentation surface
        "deprecated",  # quarantined legacy surface with cleanup tracked
        "governance_tooling",  # CI/governance/audit code; measured via RVG/audit harness
        "deferred_production",  # production; not yet in a coverage profile; tracked debt
    }
)


def _root(pkg: str) -> str:
    """Top-level package root of a find-pattern (e.g. ``core.foo`` → ``core``)."""
    return pkg.split(".", 1)[0].rstrip("*").rstrip(".")


def packaged_roots(pyproject: dict[str, Any]) -> list[str]:
    include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    return sorted({_root(p) for p in include if _root(p)})


def _coveragerc_sources(path: Path) -> set[str]:
    """Top-level source roots declared under ``[run] source`` in a coveragerc."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_option("run", "source"):
        return set()
    raw = parser.get("run", "source")
    roots: set[str] = set()
    for line in raw.splitlines():
        entry = line.strip()
        # Skip omit-style globs / non-package entries.
        if not entry or "/" in entry or "*" in entry or entry.endswith(".py"):
            continue
        roots.add(_root(entry))
    return roots


def coverage_sources(pyproject: dict[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    """Union of source roots across every coverage profile + per-profile detail."""
    detail: dict[str, list[str]] = {}
    union: set[str] = set()

    pp = [_root(s) for s in pyproject["tool"]["coverage"]["run"]["source"]]
    detail["pyproject"] = sorted(pp)
    union.update(pp)

    for rc in sorted(REPO_ROOT.rglob("*.coveragerc")):
        if ".claude/worktrees" in str(rc):
            continue
        roots = _coveragerc_sources(rc)
        detail[str(rc.relative_to(REPO_ROOT))] = sorted(roots)
        union.update(roots)

    return sorted(union), detail


def load_allowlist() -> dict[str, dict[str, str]]:
    if not ALLOWLIST.exists():
        return {}
    data: dict[str, dict[str, str]] = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return data


def audit() -> dict[str, Any]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    roots = packaged_roots(pyproject)
    sources, per_profile = coverage_sources(pyproject)
    allowlist = load_allowlist()

    missing = [r for r in roots if r not in sources]
    allowlisted: list[dict[str, str]] = []
    forbidden: list[str] = []
    invalid_allowlist: list[str] = []

    for r in missing:
        entry = allowlist.get(r)
        if entry is None:
            forbidden.append(r)
            continue
        reason = entry.get("reason", "")
        note = entry.get("note", "").strip()
        if reason not in ALLOWED_REASONS or not note:
            invalid_allowlist.append(r)
            forbidden.append(r)
            continue
        allowlisted.append({"root": r, "reason": reason, "note": note})

    # A packaged root that has NO source directory is a stale packaging entry.
    stale_packaging = [
        r
        for r in roots
        if not (REPO_ROOT / r).is_dir() and (REPO_ROOT / f"{r}.py").exists() is False
    ]

    verdict = "PASS" if not forbidden else "FAIL"
    return {
        "schema": "geosync.coverage_surface_report.v1",
        "packaged_roots": roots,
        "coverage_sources": sources,
        "coverage_sources_by_profile": per_profile,
        "measured": [r for r in roots if r in sources],
        "missing_from_coverage": missing,
        "allowlisted": allowlisted,
        "invalid_allowlist_entries": invalid_allowlist,
        "stale_packaging_roots": stale_packaging,
        "forbidden_gaps": forbidden,
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="write report JSON to this path")
    args = parser.parse_args(argv)

    report = audit()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    print(f"verdict={report['verdict']}")
    if report["forbidden_gaps"]:
        print(f"forbidden_gaps={report['forbidden_gaps']}", file=sys.stderr)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
