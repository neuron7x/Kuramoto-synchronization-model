#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync Coverage Intelligence — the single coverage authority.

This instrument is the answer to one failure mode: a coverage *number* that
no longer corresponds to coverage *truth*. It refuses to emit a green verdict
when the evidence behind it is missing, empty, malformed, or stale, and it
maps every measured surface back to the same declared production boundary so
that one run means the same thing everywhere.

It computes, from a single ``coverage.xml`` + ``junit.xml`` pair:

  * per-surface line and branch coverage, mapped through the canonical
    ``coverage_targets.toml`` contract (reusing ``surface_contract``);
  * a global RELEASE coverage number over the full production surface;
  * a risk-weighted score that weights execution/risk/data above analytics/UI;
  * the set of production files with zero exercised lines (untested surface);
  * diff coverage for changed production lines against a git base;
  * a claim -> falsifier-test matrix derived from ``docs/CLAIMS.yaml``.

It emits machine-readable evidence and a single verdict:

  MACHINE_VERIFIED    every enforced gate passed and evidence is valid.
  MACHINE_ASSISTED    gates pass but the claim/mutation layer is incomplete.
  HUMAN_REVIEW_ONLY   evidence is missing / empty / malformed / stale; the
                      number cannot be trusted and no gate result is binding.

Exit codes (under enforcement flags):
  0  verdict acceptable for the requested gates
  1  a coverage gate failed (release / critical / diff)
  2  the claim falsifier matrix is incomplete (only with --enforce-claims)
  3  evidence invalid -> HUMAN_REVIEW_ONLY (always fail-closed)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# The tool is always invoked as
# ``python -m tools.coverage.geosync_coverage_intelligence`` from the repo root
# (Makefile + CI), so the canonical ``tools`` package is on the import path
# without any sys.path mutation (the import-architecture ratchet forbids new
# sys.path hacks).
from tools.coverage.surface_contract import (
    CoverageTargets,
    load_coverage_targets,
    map_file_to_surface,
)

# The tool lives at tools/coverage/; the repo root is two parents up.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Risk weighting: execution/risk/data failures are unsafe, analytics/UI are not.
_RISK_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

VERDICT_VERIFIED = "MACHINE_VERIFIED"
VERDICT_ASSISTED = "MACHINE_ASSISTED"
VERDICT_HUMAN = "HUMAN_REVIEW_ONLY"

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_CLAIMS_INCOMPLETE = 2
EXIT_EVIDENCE_INVALID = 3


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FileCoverage:
    """Per-file coverage parsed from coverage.xml."""

    path: str
    statements: int
    covered: int
    branches: int
    branches_covered: int
    covered_lines: frozenset[int]
    line_rate: float  # percent [0, 100]
    branch_rate: float  # percent [0, 100]


@dataclass(frozen=True)
class SurfaceCoverage:
    """Aggregated coverage for one declared surface."""

    name: str
    statements: int
    covered: int
    branches: int
    branches_covered: int
    line_rate: float
    branch_rate: float
    target_final: float
    claim_risk: str

    @property
    def meets_final(self) -> bool:
        return self.line_rate >= self.target_final


@dataclass
class EvidenceStatus:
    """Outcome of validating raw evidence before any number is trusted."""

    valid: bool
    reasons: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Evidence parsing — fail closed on anything that is not real evidence
# --------------------------------------------------------------------------- #
def _rate_to_percent(value: str | None) -> float:
    if value is None:
        return 0.0
    raw = float(value)
    # coverage.xml stores rates as fractions in [0, 1]; tolerate accidental
    # already-percent inputs without inflating a real fraction.
    return raw * 100.0 if raw <= 1.0 else raw


def _source_prefixes(root: ET.Element) -> list[str]:
    """Repo-relative prefixes implied by the ``<sources>`` block.

    coverage.py, when given several top-level ``source`` directories, emits one
    ``<source>`` per root and stores each ``class@filename`` *relative to its
    matched root* — so ``execution/oms.py`` is written as ``oms.py`` and the
    ``execution/`` prefix is lost. To rebuild a repo-relative path we need the
    set of stripped prefixes; they are exactly the source roots relative to
    their common ancestor (the repository root on the machine that produced the
    report). A single source root is already unambiguous, so we return nothing
    and the filenames are trusted as-is.
    """
    sources = [s.text.strip() for s in root.iter("source") if s.text and s.text.strip()]
    if len(sources) < 2:
        return []
    norm = [s.replace("\\", "/").rstrip("/") for s in sources]
    try:
        common = os.path.commonpath(norm)
    except ValueError:
        # Mixed absolute/relative roots have no common path; fall back to
        # treating each non-empty root as its own prefix.
        return sorted({s for s in norm if s and s != "."})
    prefixes: set[str] = set()
    for s in norm:
        rel = os.path.relpath(s, common).replace("\\", "/")
        if rel and rel != ".":
            prefixes.add(rel)
    return sorted(prefixes)


_line_count_cache: dict[str, int] = {}


def _physical_line_count(file_path: Path) -> int:
    key = str(file_path)
    cached = _line_count_cache.get(key)
    if cached is not None:
        return cached
    try:
        with file_path.open("rb") as fh:
            count = sum(1 for _ in fh)
    except OSError:
        count = -1
    _line_count_cache[key] = count
    return count


def _resolve_repo_path(
    filename: str, prefixes: list[str], repo_root: Path, max_line: int = 0
) -> str:
    """Map a (possibly source-root-stripped) coverage filename back to a
    repo-relative path.

    Trusts the filename when it already resolves at the repo root, otherwise
    re-attaches the source-root prefix that makes the file exist on disk. When
    the same stripped path exists under more than one source root (e.g.
    ``core/security/tls.py`` and ``application/security/tls.py`` both collapse
    to ``security/tls.py``), the ambiguity is broken by physical length: a file
    cannot carry coverage for a line beyond its last line, so any candidate
    shorter than ``max_line`` is rejected. If exactly one candidate survives it
    is used; otherwise we fail closed to the unprefixed path rather than guess.
    """
    norm = _normalize(filename)
    if not prefixes:
        return norm
    if (repo_root / norm).exists():
        return norm
    candidates = [f"{pre}/{norm}" for pre in prefixes if (repo_root / f"{pre}/{norm}").exists()]
    if not candidates:
        return norm
    if len(candidates) == 1:
        return candidates[0]
    viable = [c for c in candidates if _physical_line_count(repo_root / c) >= max_line]
    return viable[0] if len(viable) == 1 else norm


def parse_coverage_xml(
    path: Path, repo_root: Path | None = None
) -> tuple[list[FileCoverage], EvidenceStatus]:
    """Parse coverage.xml into per-file records, failing closed on bad input."""
    if not path.exists():
        return [], EvidenceStatus(False, [f"coverage xml missing: {path}"])
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return [], EvidenceStatus(False, [f"coverage xml empty: {path}"])
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [], EvidenceStatus(False, [f"coverage xml malformed: {exc}"])

    base = repo_root if repo_root is not None else _REPO_ROOT
    prefixes = _source_prefixes(root)
    files: list[FileCoverage] = []
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename")
        if not filename:
            continue
        lines_el = cls.find("lines")
        covered_lines: set[int] = set()
        statements = 0
        covered = 0
        branches = 0
        branches_covered = 0
        max_line = 0
        if lines_el is not None:
            for line in lines_el.findall("line"):
                statements += 1
                hits = int(line.attrib.get("hits", "0"))
                number = int(line.attrib.get("number", "0"))
                max_line = max(max_line, number)
                if hits > 0:
                    covered += 1
                    covered_lines.add(number)
                if line.attrib.get("branch") == "true":
                    cond = line.attrib.get("condition-coverage", "")
                    taken, total = _parse_condition(cond)
                    branches += total
                    branches_covered += taken
        line_rate = (covered / statements * 100.0) if statements else 0.0
        branch_rate = (branches_covered / branches * 100.0) if branches else 0.0
        files.append(
            FileCoverage(
                path=_resolve_repo_path(filename, prefixes, base, max_line),
                statements=statements,
                covered=covered,
                branches=branches,
                branches_covered=branches_covered,
                covered_lines=frozenset(covered_lines),
                line_rate=line_rate,
                branch_rate=branch_rate,
            )
        )

    if not files:
        return [], EvidenceStatus(False, [f"coverage xml has no class records: {path}"])
    total_statements = sum(f.statements for f in files)
    if total_statements == 0:
        return [], EvidenceStatus(False, ["coverage xml records zero statements"])
    return files, EvidenceStatus(True)


def _parse_condition(condition: str) -> tuple[int, int]:
    """Parse ``condition-coverage`` like ``50% (1/2)`` into (taken, total)."""
    if "(" not in condition or "/" not in condition:
        return 0, 0
    inside = condition[condition.index("(") + 1 : condition.index(")")]
    taken_str, _, total_str = inside.partition("/")
    try:
        return int(taken_str), int(total_str)
    except ValueError:
        return 0, 0


def check_staleness(
    files: Iterable[FileCoverage],
    coverage_xml: Path,
    repo_root: Path,
    skew_seconds: float,
) -> EvidenceStatus:
    """Stale if any measured source file changed AFTER coverage was recorded.

    This is the honest definition of staleness: coverage describes the code as
    it was when measured. If the code on disk is newer than the coverage
    artefact, the number describes a repository that no longer exists.
    """
    if not coverage_xml.exists():
        return EvidenceStatus(False, ["coverage xml missing for staleness check"])
    cov_mtime = coverage_xml.stat().st_mtime
    stale: list[str] = []
    for fc in files:
        src = repo_root / fc.path
        if not src.exists():
            continue
        if src.stat().st_mtime > cov_mtime + skew_seconds:
            stale.append(fc.path)
    if stale:
        sample = ", ".join(sorted(stale)[:5])
        return EvidenceStatus(
            False,
            [f"coverage is stale: {len(stale)} source file(s) newer than coverage.xml ({sample})"],
        )
    return EvidenceStatus(True)


# --------------------------------------------------------------------------- #
# Surface aggregation + scores
# --------------------------------------------------------------------------- #
def _normalize(path: str) -> str:
    norm = path.strip().replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def aggregate_surfaces(
    files: list[FileCoverage], targets: CoverageTargets
) -> dict[str, SurfaceCoverage]:
    acc: dict[str, dict[str, int]] = {}
    for fc in files:
        surface = map_file_to_surface(fc.path, targets)
        if surface is None:
            continue
        bucket = acc.setdefault(
            surface,
            {"statements": 0, "covered": 0, "branches": 0, "branches_covered": 0},
        )
        bucket["statements"] += fc.statements
        bucket["covered"] += fc.covered
        bucket["branches"] += fc.branches
        bucket["branches_covered"] += fc.branches_covered

    out: dict[str, SurfaceCoverage] = {}
    for name, b in acc.items():
        target = targets.surfaces[name]
        line_rate = (b["covered"] / b["statements"] * 100.0) if b["statements"] else 0.0
        branch_rate = (b["branches_covered"] / b["branches"] * 100.0) if b["branches"] else 0.0
        out[name] = SurfaceCoverage(
            name=name,
            statements=b["statements"],
            covered=b["covered"],
            branches=b["branches"],
            branches_covered=b["branches_covered"],
            line_rate=line_rate,
            branch_rate=branch_rate,
            target_final=target.final,
            claim_risk=target.claim_risk,
        )
    return out


def global_release_coverage(surfaces: dict[str, SurfaceCoverage]) -> float:
    total = sum(s.statements for s in surfaces.values())
    covered = sum(s.covered for s in surfaces.values())
    return (covered / total * 100.0) if total else 0.0


def global_branch_coverage(surfaces: dict[str, SurfaceCoverage]) -> float:
    total = sum(s.branches for s in surfaces.values())
    covered = sum(s.branches_covered for s in surfaces.values())
    return (covered / total * 100.0) if total else 0.0


def risk_weighted_score(surfaces: dict[str, SurfaceCoverage]) -> float:
    """Coverage weighted by claim risk: critical surfaces dominate the score."""
    num = 0.0
    den = 0.0
    for s in surfaces.values():
        weight = _RISK_WEIGHT.get(s.claim_risk.lower(), 1.0) * s.statements
        num += weight * s.line_rate
        den += weight
    return (num / den) if den else 0.0


def untested_files(files: list[FileCoverage], targets: CoverageTargets) -> list[str]:
    """Production files with executable statements but zero exercised lines."""
    out: list[str] = []
    for fc in files:
        if map_file_to_surface(fc.path, targets) is None:
            continue
        if fc.statements > 0 and fc.covered == 0:
            out.append(fc.path)
    return sorted(out)


# --------------------------------------------------------------------------- #
# Critical per-file surface (reuses critical_surface.toml schema)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CriticalResult:
    path: str
    required: float
    actual: float | None  # None => file absent from coverage evidence

    @property
    def ok(self) -> bool:
        return self.actual is not None and self.actual >= self.required


def evaluate_critical(files: list[FileCoverage], critical_toml: Path) -> list[CriticalResult]:
    if not critical_toml.exists():
        return []
    doc = tomllib.loads(critical_toml.read_text(encoding="utf-8"))
    by_path = {f.path: f for f in files}
    results: list[CriticalResult] = []
    for target in doc.get("targets", []):
        path = _normalize(str(target["path"]))
        required = float(target["min_line_rate"])
        fc = by_path.get(path)
        results.append(CriticalResult(path, required, fc.line_rate if fc else None))
    return results


# --------------------------------------------------------------------------- #
# Diff coverage
# --------------------------------------------------------------------------- #
def changed_python_lines(base: str, repo_root: Path) -> dict[str, set[int]]:
    """Return added line numbers per changed .py file vs ``base``.

    Uses ``git diff --unified=0`` and parses hunk headers. Returns an empty map
    if git is unavailable or the base is unknown — diff coverage then reports as
    "not applicable" rather than blocking.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--unified=0", f"{base}...HEAD", "--", "*.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current = _normalize(line[len("+++ b/") :])
            changed.setdefault(current, set())
        elif line.startswith("@@") and current is not None:
            # @@ -a,b +c,d @@
            plus = line.split("+", 1)[1]
            spec = plus.split(" ", 1)[0]
            start_str, _, count_str = spec.partition(",")
            start = int(start_str)
            count = int(count_str) if count_str else 1
            for n in range(start, start + count):
                changed[current].add(n)
    return {p: lns for p, lns in changed.items() if lns}


@dataclass(frozen=True)
class DiffCoverage:
    applicable: bool
    total_changed: int
    covered_changed: int

    @property
    def rate(self) -> float:
        return (self.covered_changed / self.total_changed * 100.0) if self.total_changed else 100.0


def diff_coverage(
    files: list[FileCoverage], base: str, repo_root: Path, targets: CoverageTargets
) -> DiffCoverage:
    changed = changed_python_lines(base, repo_root)
    if not changed:
        return DiffCoverage(False, 0, 0)
    by_path = {f.path: f for f in files}
    total = 0
    covered = 0
    for path, lines in changed.items():
        if map_file_to_surface(path, targets) is None:
            continue  # only production surface gates diff coverage
        fc = by_path.get(path)
        if fc is None:
            continue
        # Only count changed lines that coverage.py considers executable.
        executable = lines & _executable_lines(fc)
        total += len(executable)
        covered += len(executable & fc.covered_lines)
    return DiffCoverage(total > 0, total, covered)


def _executable_lines(fc: FileCoverage) -> set[int]:
    # coverage.xml emits a <line> only for executable statements, so the
    # executable universe of a file is covered-lines ∪ miss-lines. Miss lines
    # are captured separately during parse (see _populate_miss_lines).
    return set(fc.covered_lines) | _miss_lines.get(fc.path, set())


# Populated during parse so diff coverage can intersect against real miss lines.
_miss_lines: dict[str, set[int]] = {}


# --------------------------------------------------------------------------- #
# Claim falsifier matrix
# --------------------------------------------------------------------------- #
@dataclass
class ClaimResult:
    claim_id: str
    priority: str
    tier: str
    test_id: str | None
    test_present: bool
    test_passed: bool | None  # None => junit unavailable

    @property
    def gated(self) -> bool:
        return self.priority in {"P0", "P1"} and self.tier == "ANCHORED"

    @property
    def complete(self) -> bool:
        return self.test_present and self.test_passed is not False


def _load_yaml_claims(path: Path) -> list[dict[str, object]]:
    """Load claims from CLAIMS.yaml. Prefers PyYAML; falls back to a minimal
    parser for the subset of fields we need (id, priority, tier, falsifier)."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]

        doc = yaml.safe_load(text)
        claims = doc.get("claims", []) if isinstance(doc, dict) else []
        return [c for c in claims if isinstance(c, dict)]
    except Exception:
        return _fallback_parse_claims(text)


def _fallback_parse_claims(text: str) -> list[dict[str, object]]:
    claims: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    in_falsifier = False
    for raw in text.splitlines():
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("- id:"):
            if current is not None:
                claims.append(current)
            current = {"id": stripped.split("id:", 1)[1].strip()}
            in_falsifier = False
            continue
        if current is None:
            continue
        if stripped.startswith("priority:"):
            current["priority"] = stripped.split("priority:", 1)[1].strip()
        elif stripped.startswith("tier:"):
            current["tier"] = stripped.split("tier:", 1)[1].strip()
        elif stripped.startswith("falsifier:"):
            in_falsifier = True
        elif in_falsifier and stripped.startswith("test_id:") and indent >= 4:
            current["falsifier"] = {"test_id": stripped.split("test_id:", 1)[1].strip()}
            in_falsifier = False
    if current is not None:
        claims.append(current)
    return claims


def _load_junit_nodes(path: Path) -> tuple[dict[str, bool] | None, EvidenceStatus]:
    """Return {node_id: passed} from junit.xml, or None if unavailable."""
    if not path.exists():
        return None, EvidenceStatus(False, [f"junit missing: {path}"])
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return None, EvidenceStatus(False, [f"junit empty: {path}"])
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return None, EvidenceStatus(False, [f"junit malformed: {exc}"])
    nodes: dict[str, bool] = {}
    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        passed = case.find("failure") is None and case.find("error") is None
        nodes[f"{classname}::{name}"] = passed
        nodes[name] = passed and nodes.get(name, True)
    return nodes, EvidenceStatus(True)


def _claim_test_present(test_id: str, nodes: dict[str, bool]) -> tuple[bool, bool]:
    """Match a claim falsifier ``path::func`` against junit node ids."""
    func = test_id.rsplit("::", 1)[-1].split("[", 1)[0]
    # Exact node id match first.
    for node_id, passed in nodes.items():
        node_func = node_id.rsplit("::", 1)[-1].split("[", 1)[0]
        if node_func == func:
            return True, passed
    return False, False


def claim_matrix(
    claims_path: Path, junit_path: Path
) -> tuple[list[ClaimResult], dict[str, bool] | None]:
    claims = _load_yaml_claims(claims_path) if claims_path.exists() else []
    nodes, _ = _load_junit_nodes(junit_path)
    results: list[ClaimResult] = []
    for c in claims:
        falsifier = c.get("falsifier")
        test_id = None
        if isinstance(falsifier, dict):
            tid = falsifier.get("test_id")
            test_id = str(tid) if tid is not None else None
        if test_id and nodes is not None:
            present, passed = _claim_test_present(test_id, nodes)
            passed_opt: bool | None = passed
        elif test_id and nodes is None:
            present, passed_opt = False, None
        else:
            present, passed_opt = False, (None if nodes is None else False)
        results.append(
            ClaimResult(
                claim_id=str(c.get("id", "?")),
                priority=str(c.get("priority", "?")),
                tier=str(c.get("tier", "?")),
                test_id=test_id,
                test_present=present,
                test_passed=passed_opt,
            )
        )
    return results, nodes


# --------------------------------------------------------------------------- #
# Report writers
# --------------------------------------------------------------------------- #
def write_reports(
    out_dir: Path,
    *,
    surfaces: dict[str, SurfaceCoverage],
    release_cov: float,
    branch_cov: float,
    risk_score: float,
    untested: list[str],
    critical: list[CriticalResult],
    diff: DiffCoverage,
    claims: list[ClaimResult],
    verdict: str,
    evidence: EvidenceStatus,
    gates: dict[str, bool],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "schema_version": "2.0",
        "verdict": verdict,
        "evidence_valid": evidence.valid,
        "evidence_reasons": evidence.reasons,
        "release_line_coverage": round(release_cov, 2),
        "global_branch_coverage": round(branch_cov, 2),
        "risk_weighted_score": round(risk_score, 2),
        "gates": gates,
        "surfaces": {
            name: {
                "line_rate": round(s.line_rate, 2),
                "branch_rate": round(s.branch_rate, 2),
                "statements": s.statements,
                "target_final": s.target_final,
                "claim_risk": s.claim_risk,
                "meets_final": s.meets_final,
            }
            for name, s in sorted(surfaces.items())
        },
        "untested_file_count": len(untested),
        "critical": [
            {"path": c.path, "required": c.required, "actual": c.actual, "ok": c.ok}
            for c in critical
        ],
        "diff_coverage": {
            "applicable": diff.applicable,
            "rate": round(diff.rate, 2),
            "changed_lines": diff.total_changed,
            "covered_lines": diff.covered_changed,
        },
        "claims": {
            "total": len(claims),
            "gated": sum(1 for c in claims if c.gated),
            "gated_complete": sum(1 for c in claims if c.gated and c.complete),
        },
    }
    (out_dir / "coverage_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    risk_payload = {
        "risk_weighted_score": round(risk_score, 2),
        "weights": _RISK_WEIGHT,
        "surfaces": {
            name: {
                "claim_risk": s.claim_risk,
                "weight": _RISK_WEIGHT.get(s.claim_risk.lower(), 1.0),
                "line_rate": round(s.line_rate, 2),
                "statements": s.statements,
            }
            for name, s in sorted(surfaces.items())
        },
    }
    (out_dir / "risk_weighted_coverage.json").write_text(
        json.dumps(risk_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    claim_payload = {
        "total": len(claims),
        "claims": [
            {
                "id": c.claim_id,
                "priority": c.priority,
                "tier": c.tier,
                "test_id": c.test_id,
                "test_present": c.test_present,
                "test_passed": c.test_passed,
                "gated": c.gated,
                "complete": c.complete,
            }
            for c in sorted(claims, key=lambda x: x.claim_id)
        ],
    }
    (out_dir / "claim_test_matrix.json").write_text(
        json.dumps(claim_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    _write_gap_map(out_dir / "coverage_gap_map.md", surfaces, critical, untested, verdict)
    _write_next_tests(out_dir / "next_tests.md", surfaces, untested, critical, claims)


def _write_gap_map(
    path: Path,
    surfaces: dict[str, SurfaceCoverage],
    critical: list[CriticalResult],
    untested: list[str],
    verdict: str,
) -> None:
    lines = ["# Coverage Gap Map", "", f"Verdict: **{verdict}**", "", "## Surfaces", ""]
    lines.append("| surface | line % | branch % | target | risk | meets |")
    lines.append("|---|---|---|---|---|---|")
    for name, s in sorted(surfaces.items()):
        mark = "✅" if s.meets_final else "❌"
        lines.append(
            f"| {name} | {s.line_rate:.2f} | {s.branch_rate:.2f} | "
            f"{s.target_final:.0f} | {s.claim_risk} | {mark} |"
        )
    lines += ["", "## Critical files below threshold", ""]
    below = [c for c in critical if not c.ok]
    if not below:
        lines.append("_none_")
    for c in below:
        actual = "absent" if c.actual is None else f"{c.actual:.2f}%"
        lines.append(f"- `{c.path}` — required {c.required:.0f}%, actual {actual}")
    lines += ["", f"## Untested production files ({len(untested)})", ""]
    for p in untested[:100]:
        lines.append(f"- `{p}`")
    if len(untested) > 100:
        lines.append(f"- … and {len(untested) - 100} more")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_next_tests(
    path: Path,
    surfaces: dict[str, SurfaceCoverage],
    untested: list[str],
    critical: list[CriticalResult],
    claims: list[ClaimResult],
) -> None:
    lines = ["# Next Tests — prioritized by risk", ""]
    lines.append("## 1. Critical files below threshold (highest leverage)")
    below = [c for c in critical if not c.ok]
    if not below:
        lines.append("- _none_")
    for c in below:
        lines.append(f"- `{c.path}` → reach {c.required:.0f}% line coverage")
    lines += ["", "## 2. Gated claims missing a passing falsifier test"]
    missing = [c for c in claims if c.gated and not c.complete]
    if not missing:
        lines.append("- _none_")
    for c in missing:
        lines.append(f"- `{c.claim_id}` ({c.priority}/{c.tier}) → test_id `{c.test_id}`")
    lines += ["", "## 3. Surfaces below final target (ranked by risk weight)"]
    ranked = sorted(
        (s for s in surfaces.values() if not s.meets_final),
        key=lambda s: _RISK_WEIGHT.get(s.claim_risk.lower(), 1.0),
        reverse=True,
    )
    if not ranked:
        lines.append("- _none_")
    for s in ranked:
        gap = s.target_final - s.line_rate
        lines.append(
            f"- `{s.name}` — {s.line_rate:.2f}% / {s.target_final:.0f}% "
            f"(gap {gap:.2f}, risk {s.claim_risk})"
        )
    lines += ["", f"## 4. Untested production files ({len(untested)})"]
    for p in untested[:50]:
        lines.append(f"- `{p}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    coverage_xml = Path(args.coverage)
    out_dir = Path(args.out)

    files, evidence = parse_coverage_xml(coverage_xml, repo_root)
    # Record miss lines for diff intersection: re-parse to capture non-covered.
    _populate_miss_lines(coverage_xml, repo_root)

    if evidence.valid and args.check_staleness:
        stale = check_staleness(files, coverage_xml, repo_root, args.staleness_skew_seconds)
        if not stale.valid:
            evidence = EvidenceStatus(False, evidence.reasons + stale.reasons)

    targets = load_coverage_targets(Path(args.targets))

    if not evidence.valid:
        # Fail closed: write a HUMAN_REVIEW_ONLY verdict with whatever we have.
        write_reports(
            out_dir,
            surfaces={},
            release_cov=0.0,
            branch_cov=0.0,
            risk_score=0.0,
            untested=[],
            critical=[],
            diff=DiffCoverage(False, 0, 0),
            claims=[],
            verdict=VERDICT_HUMAN,
            evidence=evidence,
            gates={"evidence": False},
        )
        _print_verdict(VERDICT_HUMAN, evidence, None)
        return EXIT_EVIDENCE_INVALID

    surfaces = aggregate_surfaces(files, targets)
    release_cov = global_release_coverage(surfaces)
    branch_cov = global_branch_coverage(surfaces)
    risk_score = risk_weighted_score(surfaces)
    untested = untested_files(files, targets)
    critical = evaluate_critical(files, Path(args.critical))
    diff = diff_coverage(files, args.diff_base, repo_root, targets)
    claims, _ = claim_matrix(Path(args.claims), Path(args.junit))

    release_gate = targets.global_thresholds["current_release_gate"]
    diff_gate = targets.global_thresholds["diff_coverage_gate"]

    gates = {
        "release_90": release_cov >= release_gate,
        "critical_surface": all(c.ok for c in critical) if critical else True,
        "diff_90": (diff.rate >= diff_gate) if diff.applicable else True,
    }
    claims_complete = all(c.complete for c in claims if c.gated)

    # Evidence is valid here (we returned early otherwise), so the worst case
    # is MACHINE_ASSISTED: the run is real, but a gate or the claim matrix is
    # not yet complete. HUMAN_REVIEW_ONLY is reserved for untrustworthy
    # evidence — never for an honest red gate.
    if all(gates.values()) and claims_complete:
        verdict = VERDICT_VERIFIED
    else:
        verdict = VERDICT_ASSISTED

    write_reports(
        out_dir,
        surfaces=surfaces,
        release_cov=release_cov,
        branch_cov=branch_cov,
        risk_score=risk_score,
        untested=untested,
        critical=critical,
        diff=diff,
        claims=claims,
        verdict=verdict,
        evidence=evidence,
        gates=gates,
    )
    _print_verdict(verdict, evidence, (release_cov, gates, diff, claims_complete))

    # Exit-code policy
    if args.enforce_release_90 or args.enforce_critical or args.enforce_diff:
        gate_failed = False
        if args.enforce_release_90 and not gates["release_90"]:
            gate_failed = True
        if args.enforce_critical and not gates["critical_surface"]:
            gate_failed = True
        if args.enforce_diff and not gates["diff_90"]:
            gate_failed = True
        if gate_failed:
            return EXIT_GATE_FAILED
    if args.enforce_claims and not claims_complete:
        return EXIT_CLAIMS_INCOMPLETE
    return EXIT_OK


def _populate_miss_lines(coverage_xml: Path, repo_root: Path | None = None) -> None:
    _miss_lines.clear()
    if not coverage_xml.exists():
        return
    try:
        root = ET.fromstring(coverage_xml.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError:
        return
    base = repo_root if repo_root is not None else _REPO_ROOT
    prefixes = _source_prefixes(root)
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename")
        if not filename:
            continue
        lines_el = cls.find("lines")
        if lines_el is None:
            continue
        all_numbers = [int(line.attrib.get("number", "0")) for line in lines_el.findall("line")]
        misses = {
            int(line.attrib.get("number", "0"))
            for line in lines_el.findall("line")
            if int(line.attrib.get("hits", "0")) == 0
        }
        if misses:
            max_line = max(all_numbers) if all_numbers else 0
            resolved = _resolve_repo_path(filename, prefixes, base, max_line)
            _miss_lines[resolved] = misses


def _print_verdict(
    verdict: str,
    evidence: EvidenceStatus,
    detail: tuple[float, dict[str, bool], DiffCoverage, bool] | None,
) -> None:
    print(f"VERDICT: {verdict}")
    if not evidence.valid:
        for reason in evidence.reasons:
            print(f"  evidence: {reason}")
        return
    if detail is None:
        return
    release_cov, gates, diff, claims_complete = detail
    print(f"  release line coverage: {release_cov:.2f}%")
    for name, ok in gates.items():
        print(f"  gate {name}: {'PASS' if ok else 'FAIL'}")
    if diff.applicable:
        print(f"  diff coverage: {diff.rate:.2f}% ({diff.covered_changed}/{diff.total_changed})")
    print(f"  gated claims complete: {claims_complete}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GeoSync Coverage Intelligence authority")
    p.add_argument("--coverage", default="reports/coverage/coverage.xml")
    p.add_argument("--junit", default="reports/coverage/junit.xml")
    p.add_argument("--targets", default="configs/quality/coverage_targets.toml")
    p.add_argument("--critical", default="configs/quality/critical_surface.toml")
    p.add_argument("--claims", default="docs/CLAIMS.yaml")
    p.add_argument("--out", default="reports/coverage")
    p.add_argument("--repo-root", default=str(_REPO_ROOT))
    p.add_argument("--diff-base", default="origin/main")
    p.add_argument("--check-staleness", action="store_true", default=True)
    p.add_argument("--no-check-staleness", dest="check_staleness", action="store_false")
    p.add_argument("--staleness-skew-seconds", type=float, default=2.0)
    p.add_argument("--enforce-release-90", action="store_true")
    p.add_argument("--enforce-critical", action="store_true")
    p.add_argument("--enforce-diff", action="store_true")
    p.add_argument("--enforce-claims", action="store_true")
    p.add_argument("--suggest-tests", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
