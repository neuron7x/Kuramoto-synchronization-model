#!/usr/bin/env python3
"""Emit a per-component coverage + mutation test-strength report.

Coverage says what executed; mutation says whether the tests detect wrong
behaviour. A component is only "strongly tested" when BOTH are present:

    line_coverage    = covered_lines / num_statements * 100
    branch_coverage  = covered_branches / num_branches * 100
    mutation_score   = killed / (killed + survived) * 100
    oracle_gap       = branch_coverage - mutation_score
    verified_test_strength = min(branch_coverage, mutation_score)

Inputs:
  * a coverage.py JSON report (per-file summary), grouped by component root;
  * optional mutation artifacts ``artifacts/test_strength/mutation.<name>.json``
    (normalized by tools/rvg_normalize_mutation.py).

Fail-closed: a packaged component with no coverage data is a forbidden gap; a
component whose mutation artifact reports zero valid mutants or inconsistent
counts is FAIL; strength is never claimed from coverage alone.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_ID = "geosync.component_strength_report.v1"
ORACLE_GAP_MAX = 15.0

# component name -> coverage profile it is (or should be) measured under.
DEFAULT_COMPONENTS: dict[str, str] = {
    "libs": "configs/quality/release_90.coveragerc",
    "modules": "configs/quality/release_90.coveragerc",
    "geosync_pro": "configs/quality/release_90.coveragerc",
    "execution": "configs/quality/release_90.coveragerc",
    "backtest": "configs/quality/release_90.coveragerc",
    "core": "configs/quality/release_90.coveragerc",
    "application": "configs/quality/release_90.coveragerc",
}


def _pct(num: int, den: int) -> float:
    return round(num / den * 100.0, 2) if den else 0.0


def _component_coverage(coverage: dict[str, Any], name: str) -> tuple[int, int, int, int]:
    """Sum (covered_lines, num_statements, covered_branches, num_branches) for a root."""
    cl = ns = cb = nb = 0
    prefix = name + "/"
    for path, entry in coverage.get("files", {}).items():
        norm = path.replace("\\", "/")
        if norm == name or norm.startswith(prefix):
            s = entry.get("summary", {})
            cl += int(s.get("covered_lines", 0))
            ns += int(s.get("num_statements", 0))
            cb += int(s.get("covered_branches", 0))
            nb += int(s.get("num_branches", 0))
    return cl, ns, cb, nb


def _load_mutation(mutation_dir: Path, name: str) -> dict[str, Any] | None:
    path = mutation_dir / f"mutation.{name}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_component(
    name: str,
    profile: str,
    coverage: dict[str, Any],
    mutation_dir: Path,
) -> dict[str, Any]:
    cl, ns, cb, nb = _component_coverage(coverage, name)
    measured = ns > 0
    line_cov = _pct(cl, ns)
    branch_cov = _pct(cb, nb) if nb else line_cov

    mut = _load_mutation(mutation_dir, name)
    mutation_tool: str | None = None
    killed = survived = valid = 0
    mutation_score: float | None = None
    unsound_mutation = False

    if mut is not None and not mut.get("bootstrap_report_only"):
        mutation_tool = str(mut.get("tool", "unknown"))
        killed = int(mut.get("killed", 0))
        survived = int(mut.get("survived", 0))
        valid = int(mut.get("valid_mutants", killed + survived))
        if valid <= 0 or killed + survived != valid:
            unsound_mutation = True
        else:
            mutation_score = _pct(killed, valid)

    if not measured:
        strength_class = "UNMEASURED"
    elif mutation_score is not None:
        strength_class = "MUTATION_VERIFIED"
    else:
        strength_class = "COVERAGE_ONLY"

    oracle_gap = round(branch_cov - mutation_score, 2) if mutation_score is not None else None
    vts = round(min(branch_cov, mutation_score), 2) if mutation_score is not None else None

    # Fail-closed: strength is PASS only when mutation-verified, sound, and the
    # oracle gap is within bound. Unmeasured or unsound-mutation components FAIL;
    # coverage-only is honestly not a PASS (visibility != verified strength).
    verdict = "FAIL"
    if strength_class == "MUTATION_VERIFIED" and not unsound_mutation:
        if oracle_gap is not None and oracle_gap <= ORACLE_GAP_MAX:
            verdict = "PASS"

    return {
        "name": name,
        "coverage_profile": profile,
        "line_coverage": line_cov,
        "branch_coverage": branch_cov,
        "line_coverage_raw": [cl, ns],
        "branch_coverage_raw": [cb, nb],
        "mutation_tool": mutation_tool,
        "killed": killed,
        "survived": survived,
        "valid_mutants": valid,
        "mutation_score": mutation_score,
        "oracle_gap": oracle_gap,
        "verified_test_strength": vts,
        "strength_class": strength_class,
        "verdict": verdict,
    }


def build_report(
    coverage: dict[str, Any],
    mutation_dir: Path,
    components: dict[str, str],
) -> dict[str, Any]:
    comps = [build_component(n, p, coverage, mutation_dir) for n, p in sorted(components.items())]
    forbidden = [c["name"] for c in comps if c["strength_class"] == "UNMEASURED"]
    overall = "PASS" if all(c["verdict"] == "PASS" for c in comps) and not forbidden else "FAIL"
    return {
        "schema": SCHEMA_ID,
        "components": comps,
        "forbidden_gaps": forbidden,
        "verdict": overall,
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    """Process exit code for a strength report.

    Fail-closed: a FAIL verdict exits non-zero unless the run is explicitly
    non-enforcing (``report_only``). This is the whole point of the gate — a
    report that can say FAIL while the command exits 0 is epistemically unsafe.
    """

    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Component test-strength report")
    p.add_argument("--coverage", required=True, help="coverage.py JSON report")
    p.add_argument(
        "--mutation-dir", default="artifacts/test_strength", help="dir of mutation.<name>.json"
    )
    p.add_argument("--out", help="write report JSON here (else stdout)")
    p.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "non-enforcing mode: always exit 0 but stamp the artifact "
            "report_only=true. Without it a FAIL verdict exits non-zero."
        ),
    )
    args = p.parse_args(argv)

    coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    report = build_report(coverage, Path(args.mutation_dir), DEFAULT_COMPONENTS)
    # Record the enforcement mode ON the artifact so a downstream verdict
    # aggregator cannot mistake a non-enforcing run for a passing gate.
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"component-strength verdict: {report['verdict']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
