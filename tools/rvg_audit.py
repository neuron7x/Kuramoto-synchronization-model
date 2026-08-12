#!/usr/bin/env python3
"""RVG-1 Repository Verification Gate — deterministic audit verdict engine.

Reads raw audit artifacts (coverage, junit, mutation, lint, type, security,
SBOM), recomputes every percentage from raw numerator/denominator, cross-checks
against tool-reported values, applies fail-closed thresholds, and emits a
machine-readable verdict (JSON) plus a human-readable report (Markdown).

Design invariants (see audit/RVG_PROTOCOL.md):
  * No invented metrics. Every percentage carries an explicit numerator and
    denominator, both surfaced in the verdict.
  * Missing required evidence => FAIL (fail-closed).
  * Zero denominator => FAIL (never divides silently).
  * Percentages are recomputed here from raw counts, never trusted from a tool
    summary line; a cross-check compares recompute vs reported and fails on
    delta > CROSS_CHECK_TOLERANCE.
  * Deterministic: no wall-clock, randomness, or environment leakage except the
    caller-supplied --timestamp / --commit / --python-version fields.

Stdlib-only (json, xml.etree, argparse, pathlib) so the gate has no runtime
dependency surface of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CROSS_CHECK_TOLERANCE = 0.01

# Fields in a verdict that legitimately vary between two otherwise-identical
# audit runs (used by the reproducibility check in rvg_verify_artifacts.py).
NONDETERMINISTIC_FIELDS = ("timestamp_utc", "commit", "python_version")


class AuditError(Exception):
    """Raised on any fail-closed condition. Message becomes a fail reason."""


def _pct(numerator: float, denominator: float, *, what: str) -> float:
    """Percentage with fail-closed zero-denominator guard, rounded to 2 dp."""
    if denominator == 0:
        raise AuditError(f"{what}: zero denominator (cannot compute percentage)")
    if numerator < 0 or denominator < 0:
        raise AuditError(
            f"{what}: negative count (numerator={numerator}, denominator={denominator})"
        )
    return round(numerator / denominator * 100.0, 2)


def _load_json(path: Path, *, what: str) -> Any:
    if not path.is_file():
        raise AuditError(f"{what}: required artifact missing at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditError(f"{what}: invalid JSON at {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Metric extractors
# --------------------------------------------------------------------------- #
@dataclass
class Metric:
    """A single evidence percentage bound to its raw counts."""

    value: float
    numerator: float
    denominator: float

    def cross_check(self, reported: float | None, *, what: str) -> None:
        """Recompute from raw and compare against a tool-reported value."""
        recomputed = _pct(self.numerator, self.denominator, what=what)
        if abs(recomputed - self.value) > CROSS_CHECK_TOLERANCE:
            raise AuditError(f"{what}: internal recompute mismatch ({recomputed} vs {self.value})")
        if reported is not None and abs(recomputed - reported) > CROSS_CHECK_TOLERANCE:
            raise AuditError(
                f"{what}: reported value {reported} disagrees with recompute "
                f"{recomputed} (delta > {CROSS_CHECK_TOLERANCE})"
            )


def coverage_metrics(cov: dict[str, Any]) -> tuple[Metric, Metric]:
    """Return (line_coverage, branch_coverage) Metrics from coverage.py JSON.

    coverage.py totals expose covered_lines/num_statements and
    covered_branches/num_branches. Line and branch percentages are computed
    independently from those raw counts. The combined coverage.py
    ``percent_covered`` is cross-checked separately by the caller.
    """
    totals = cov.get("totals")
    if not isinstance(totals, dict):
        raise AuditError("coverage: missing 'totals' block")

    covered_lines = totals.get("covered_lines")
    num_statements = totals.get("num_statements")
    if covered_lines is None or num_statements is None:
        raise AuditError("coverage: missing covered_lines/num_statements")
    line = Metric(
        value=_pct(covered_lines, num_statements, what="line_coverage"),
        numerator=covered_lines,
        denominator=num_statements,
    )

    num_branches = totals.get("num_branches")
    covered_branches = totals.get("covered_branches")
    if num_branches is None or covered_branches is None:
        raise AuditError(
            "coverage: missing num_branches/covered_branches (run pytest with --cov-branch)"
        )
    branch = Metric(
        value=_pct(covered_branches, num_branches, what="branch_coverage"),
        numerator=covered_branches,
        denominator=num_branches,
    )
    return line, branch


def coverage_combined_reported(cov: dict[str, Any]) -> float | None:
    """coverage.py's own combined percent_covered, for an extra cross-check."""
    totals = cov.get("totals", {})
    val = totals.get("percent_covered")
    return round(float(val), 2) if val is not None else None


def mutation_metric(mut: dict[str, Any]) -> Metric:
    """Return mutation_score Metric from a normalized mutation.json."""
    killed = mut.get("killed")
    survived = mut.get("survived")
    if killed is None or survived is None:
        raise AuditError("mutation: missing killed/survived counts")
    valid = mut.get("valid_mutants")
    if valid is None:
        valid = killed + survived
    if valid != killed + survived:
        raise AuditError(
            f"mutation: valid_mutants ({valid}) != killed+survived ({killed}+{survived})"
        )
    if valid == 0:
        raise AuditError("mutation: valid_mutants = 0 (no oracle signal)")
    return Metric(
        value=_pct(killed, valid, what="mutation_score"),
        numerator=killed,
        denominator=valid,
    )


def junit_counts(path: Path) -> dict[str, int]:
    """Aggregate tests/failures/errors/skipped across all testsuites."""
    if not path.is_file():
        raise AuditError(f"junit: required artifact missing at {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AuditError(f"junit: invalid XML at {path}: {exc}") from exc

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise AuditError("junit: no <testsuite> elements found")

    agg = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in agg:
            agg[key] += int(suite.get(key, 0) or 0)
    return agg


def ruff_error_count(path: Path) -> int:
    """Number of ruff findings (json array of diagnostics)."""
    data = _load_json(path, what="ruff")
    if isinstance(data, list):
        return len(data)
    raise AuditError("ruff: expected a JSON array of diagnostics")


def mypy_error_count(path: Path) -> int:
    """Number of mypy 'error:' lines in the captured output."""
    if not path.is_file():
        raise AuditError(f"mypy: required artifact missing at {path}")
    text = path.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if ": error:" in line)


@dataclass
class VulnCounts:
    """Vulnerability tally with an HONEST severity split.

    ``high_critical`` counts ONLY advisories whose severity is explicitly high
    or critical. Advisories with missing/unrecognized severity are counted in
    ``unknown`` — never silently promoted to high/critical (that would be an
    unprovenanced metric). The protocol §14 gate keys on ``high_critical``.
    """

    high_critical: int = 0
    unknown: int = 0

    @property
    def total(self) -> int:
        return self.high_critical + self.unknown


def pip_audit_vulns(path: Path) -> VulnCounts:
    """Count vulns in a pip-audit JSON report, split by explicit severity."""
    data = _load_json(path, what="pip-audit")
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    counts = VulnCounts()
    for dep in deps if isinstance(deps, list) else []:
        for vuln in dep.get("vulns", []) if isinstance(dep, dict) else []:
            sev = str(vuln.get("severity", "")).lower()
            if sev in ("high", "critical"):
                counts.high_critical += 1
            else:
                # pip-audit / PyPI advisories frequently omit severity. Record
                # the vuln, but do NOT claim it is high/critical without evidence.
                counts.unknown += 1
    return counts


def osv_vulns(path: Path) -> VulnCounts:
    """Count vulns in an osv-scanner JSON report, split by explicit severity."""
    data = _load_json(path, what="osv")
    counts = VulnCounts()
    for res in data.get("results", []) if isinstance(data, dict) else []:
        for pkg in res.get("packages", []):
            for vuln in pkg.get("vulnerabilities", []):
                sev_entries = vuln.get("severity", []) or []
                labels = " ".join(str(s.get("type", "")) for s in sev_entries).lower()
                db = str(vuln.get("database_specific", {}).get("severity", "")).lower()
                if "critical" in db or "high" in db or "critical" in labels or "high" in labels:
                    counts.high_critical += 1
                else:
                    counts.unknown += 1
    return counts


def sbom_present(path: Path) -> bool:
    """True only for a real CycloneDX SBOM carrying at least one component.

    An empty ``components: []`` placeholder (what the Makefile used to emit when
    cyclonedx-py was absent) is NOT a dependency inventory and must fail closed —
    otherwise the SBOM gate passes with zero supply-chain evidence.
    """
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if data.get("bomFormat") != "CycloneDX":
        return False
    components = data.get("components")
    return isinstance(components, list) and len(components) > 0


# --------------------------------------------------------------------------- #
# Verdict assembly
# --------------------------------------------------------------------------- #
@dataclass
class Thresholds:
    line_coverage: float = 90.0
    branch_coverage: float = 85.0
    mutation_score: float = 75.0
    oracle_gap: float = 15.0

    @classmethod
    def load(cls, path: Path | None) -> "Thresholds":
        if path is None:
            return cls()
        data = _load_json(path, what="thresholds")
        gates = data.get("critical_gates", data)
        return cls(
            line_coverage=float(gates.get("line_coverage", cls.line_coverage)),
            branch_coverage=float(gates.get("branch_coverage", cls.branch_coverage)),
            mutation_score=float(gates.get("mutation_score", cls.mutation_score)),
            oracle_gap=float(gates.get("oracle_gap", cls.oracle_gap)),
        )


@dataclass
class Verdict:
    fields: dict[str, Any] = field(default_factory=dict)
    fail_reasons: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.fail_reasons


def compute_verdict(
    *,
    coverage_path: Path,
    junit_path: Path,
    mutation_path: Path,
    ruff_path: Path | None,
    mypy_path: Path | None,
    pip_audit_path: Path | None,
    osv_path: Path | None,
    sbom_path: Path | None,
    thresholds: Thresholds,
    hash_manifest_present: bool,
    repo: str,
    commit: str,
    timestamp_utc: str,
    python_version: str,
) -> Verdict:
    v = Verdict()
    reasons = v.fail_reasons
    f = v.fields

    f.update(
        repo=repo,
        commit=commit,
        timestamp_utc=timestamp_utc,
        python_version=python_version,
    )

    # --- Test evidence (each guarded independently so one gap doesn't mask others) ---
    line = branch = mutation = None

    try:
        cov = _load_json(coverage_path, what="coverage")
        line, branch = coverage_metrics(cov)
        line.cross_check(None, what="line_coverage")
        branch.cross_check(None, what="branch_coverage")
        f["line_coverage"] = line.value
        f["line_coverage_raw"] = [line.numerator, line.denominator]
        f["branch_coverage"] = branch.value
        f["branch_coverage_raw"] = [branch.numerator, branch.denominator]
    except AuditError as exc:
        reasons.append(str(exc))

    try:
        junit = junit_counts(junit_path)
        collected = junit["tests"]
        failed = junit["failures"] + junit["errors"]
        skipped = junit["skipped"]
        passed = collected - failed - skipped
        f["tests_collected"] = collected
        f["tests_passed"] = passed
        f["tests_failed"] = failed
        f["tests_skipped"] = skipped
        if collected == 0:
            reasons.append("tests: zero tests collected")
        else:
            rate = _pct(passed, collected, what="test_pass_rate")
            f["test_pass_rate"] = rate
            f["test_pass_rate_raw"] = [passed, collected]
        if failed > 0:
            reasons.append(f"tests: {failed} failing/erroring test(s)")
    except AuditError as exc:
        reasons.append(str(exc))

    try:
        mut = _load_json(mutation_path, what="mutation")
        if mut.get("bootstrap_report_only"):
            # Explicitly non-enforcing bootstrap evidence: no mutation run was
            # performed, so NO mutation_score is claimed and the mutation gate is
            # not applied. This is honest absence, not a fabricated `tool: none`
            # score. `rvg_assert_verdict.py --mode enforce` rejects it; --mode
            # bootstrap accepts it. See audit/RVG_PROTOCOL.md §6 / P1-2.
            f["mutation_bootstrap_report_only"] = True
            f["mutation_tool"] = str(mut.get("tool", "none"))
        else:
            mutation = mutation_metric(mut)
            mutation.cross_check(mut.get("mutation_score"), what="mutation_score")
            f["mutation_score"] = mutation.value
            f["mutation_score_raw"] = [mutation.numerator, mutation.denominator]
            f["mutation_tool"] = str(mut.get("tool", "unknown"))
            for extra in ("timeout", "incompetent"):
                if extra in mut:
                    f[f"mutation_{extra}"] = mut[extra]
    except AuditError as exc:
        reasons.append(str(exc))

    # --- Derived metrics (only when both inputs exist) ---
    if branch is not None and mutation is not None:
        gap = round(branch.value - mutation.value, 2)
        vts = round(min(branch.value, mutation.value), 2)
        f["oracle_gap"] = gap
        f["verified_test_strength"] = vts
        if gap > thresholds.oracle_gap:
            reasons.append(
                f"oracle_gap {gap} > {thresholds.oracle_gap} "
                "(execution outruns behavioral verification)"
            )

    # --- Threshold gates ---
    if line is not None and line.value < thresholds.line_coverage:
        reasons.append(f"line_coverage {line.value} < {thresholds.line_coverage}")
    if branch is not None and branch.value < thresholds.branch_coverage:
        reasons.append(f"branch_coverage {branch.value} < {thresholds.branch_coverage}")
    if mutation is not None and mutation.value < thresholds.mutation_score:
        reasons.append(f"mutation_score {mutation.value} < {thresholds.mutation_score}")

    # --- Static quality ---
    if ruff_path is not None:
        try:
            n = ruff_error_count(ruff_path)
            f["ruff_errors"] = n
            if n > 0:
                reasons.append(f"ruff: {n} finding(s)")
        except AuditError as exc:
            reasons.append(str(exc))
    if mypy_path is not None:
        try:
            n = mypy_error_count(mypy_path)
            f["mypy_errors"] = n
            if n > 0:
                reasons.append(f"mypy: {n} error(s)")
        except AuditError as exc:
            reasons.append(str(exc))

    # --- Supply chain ---
    high_crit = 0
    unknown_sev = 0
    if pip_audit_path is not None:
        try:
            c = pip_audit_vulns(pip_audit_path)
            f["pip_audit_high_critical"] = c.high_critical
            f["pip_audit_unknown_severity"] = c.unknown
            high_crit += c.high_critical
            unknown_sev += c.unknown
        except AuditError as exc:
            reasons.append(str(exc))
    if osv_path is not None:
        try:
            c = osv_vulns(osv_path)
            f["osv_high_critical"] = c.high_critical
            f["osv_unknown_severity"] = c.unknown
            high_crit += c.high_critical
            unknown_sev += c.unknown
        except AuditError as exc:
            reasons.append(str(exc))
    f["high_vulnerabilities"] = high_crit
    f["critical_vulnerabilities"] = high_crit  # merged high+critical bucket
    f["unknown_severity_vulnerabilities"] = unknown_sev
    # Gate keys on explicit high/critical (protocol §14). Unknown-severity
    # advisories are surfaced for triage but not asserted as high/critical.
    if high_crit > 0:
        reasons.append(f"supply-chain: {high_crit} high/critical vulnerability(ies)")

    present = sbom_present(sbom_path) if sbom_path is not None else False
    f["sbom_present"] = present
    if not present:
        reasons.append("sbom: not generated")

    f["hash_manifest_present"] = hash_manifest_present
    if not hash_manifest_present:
        reasons.append("hash-manifest: audit.hashes not generated")

    f["verdict"] = "PASS" if v.passed else "FAIL"
    f["fail_reasons"] = list(reasons)

    if reasons:
        v.next_actions = _next_actions(reasons)
    return v


def _next_actions(reasons: list[str]) -> list[str]:
    actions: list[str] = []
    for r in reasons:
        if r.startswith("line_coverage") or r.startswith("branch_coverage"):
            actions.append("Add tests to raise executed line/branch coverage above the gate.")
        elif r.startswith("mutation_score"):
            actions.append("Strengthen assertions / add oracles to kill surviving mutants.")
        elif r.startswith("oracle_gap"):
            actions.append("Close oracle gap: coverage executes code the tests do not verify.")
        elif r.startswith("tests:"):
            actions.append("Fix failing tests before the gate can pass.")
        elif r.startswith("ruff") or r.startswith("mypy"):
            actions.append("Resolve static-quality findings (ruff/mypy).")
        elif r.startswith("supply-chain"):
            actions.append("Remediate or justify high/critical dependency vulnerabilities.")
        elif r.startswith("sbom") or r.startswith("hash-manifest"):
            actions.append("Regenerate missing audit provenance artifact.")
        else:
            actions.append(f"Resolve: {r}")
    # dedupe preserving order
    seen: set[str] = set()
    return [a for a in actions if not (a in seen or seen.add(a))]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_markdown(v: Verdict) -> str:
    f = v.fields

    def g(key: str, default: str = "n/a") -> str:
        return str(f.get(key, default))

    lines = [
        "# RVG VERDICT",
        "",
        f"Commit: {g('commit')}",
        f"Date UTC: {g('timestamp_utc')}",
        f"Environment: {g('python_version')}",
        "",
        "## Test Evidence",
        "",
        f"- Tests collected: {g('tests_collected')}",
        f"- Tests passed: {g('tests_passed')}",
        f"- Test pass rate: {g('test_pass_rate')}%",
        f"- Line coverage: {g('line_coverage')}%",
        f"- Branch coverage: {g('branch_coverage')}%",
        f"- Mutation score: {g('mutation_score')}%",
        f"- Oracle gap: {g('oracle_gap')}%",
        f"- Verified test strength: {g('verified_test_strength')}%",
        "",
        "## Static Quality",
        "",
        f"- Ruff errors: {g('ruff_errors')}",
        f"- Mypy errors: {g('mypy_errors')}",
        "",
        "## Supply Chain",
        "",
        f"- pip-audit high/critical: {g('pip_audit_high_critical')}",
        f"- OSV high/critical: {g('osv_high_critical')}",
        f"- Unknown-severity advisories: {g('unknown_severity_vulnerabilities')}",
        f"- SBOM: {'present' if f.get('sbom_present') else 'missing'}",
        f"- Hash manifest: {'present' if f.get('hash_manifest_present') else 'missing'}",
        "",
        "## Verdict",
        "",
        g("verdict"),
        "",
        "## Fail Reasons",
        "",
    ]
    if v.fail_reasons:
        lines += [f"{i}. {r}" for i, r in enumerate(v.fail_reasons, 1)]
    else:
        lines.append("None.")
    lines += ["", "## Required Next Actions", ""]
    if v.next_actions:
        lines += [f"{i}. {a}" for i, a in enumerate(v.next_actions, 1)]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _opt_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RVG-1 audit verdict engine")
    p.add_argument("--coverage", required=True)
    p.add_argument("--junit", required=True)
    p.add_argument("--mutation", required=True)
    p.add_argument("--ruff")
    p.add_argument("--mypy")
    p.add_argument("--pip-audit")
    p.add_argument("--osv")
    p.add_argument("--sbom")
    p.add_argument("--thresholds")
    p.add_argument(
        "--hash-manifest", help="path to audit.hashes; presence => hash_manifest_present"
    )
    p.add_argument("--repo", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--timestamp", default="", help="caller-supplied UTC timestamp (determinism)")
    p.add_argument("--python-version", default="")
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = Thresholds.load(_opt_path(args.thresholds))
    hash_manifest = _opt_path(args.hash_manifest)
    v = compute_verdict(
        coverage_path=Path(args.coverage),
        junit_path=Path(args.junit),
        mutation_path=Path(args.mutation),
        ruff_path=_opt_path(args.ruff),
        mypy_path=_opt_path(args.mypy),
        pip_audit_path=_opt_path(args.pip_audit),
        osv_path=_opt_path(args.osv),
        sbom_path=_opt_path(args.sbom),
        thresholds=thresholds,
        hash_manifest_present=bool(hash_manifest and hash_manifest.is_file()),
        repo=args.repo,
        commit=args.commit,
        timestamp_utc=args.timestamp,
        python_version=args.python_version,
    )
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(v.fields, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.out_md).write_text(render_markdown(v), encoding="utf-8")

    print(f"RVG verdict: {v.fields['verdict']}")
    for r in v.fail_reasons:
        print(f"  FAIL: {r}")
    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main())
