# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contracts for the component test-strength report generator.

Coverage visibility is not verified strength. This proves the generator computes
line/branch/mutation/oracle_gap/verified_test_strength from raw counts, classes a
component MUTATION_VERIFIED / COVERAGE_ONLY / UNMEASURED, fails closed on unsound
mutation evidence, and emits a schema-valid artifact.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "audit" / "schema" / "component_strength_report.schema.json"
TOOL = ROOT / "tools" / "audit_component_strength.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("acs_strength", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


acs = _load_tool()


def _coverage(files: dict[str, tuple[int, int, int, int]]) -> dict:
    return {
        "files": {
            path: {
                "summary": {
                    "covered_lines": cl,
                    "num_statements": ns,
                    "covered_branches": cb,
                    "num_branches": nb,
                }
            }
            for path, (cl, ns, cb, nb) in files.items()
        }
    }


def test_mutation_verified_component_computes_all_formulas(tmp_path) -> None:
    cov = _coverage({"libs/db/retry.py": (90, 100, 42, 50)})
    (tmp_path / "mutation.libs.json").write_text(
        json.dumps({"tool": "mutmut", "killed": 80, "survived": 20, "valid_mutants": 100})
    )
    c = acs.build_component("libs", "p", cov, tmp_path)
    assert c["line_coverage"] == 90.0
    assert c["branch_coverage"] == 84.0  # 42/50
    assert c["mutation_score"] == 80.0
    assert c["oracle_gap"] == 4.0  # 84 - 80
    assert c["verified_test_strength"] == 80.0  # min(84, 80)
    assert c["strength_class"] == "MUTATION_VERIFIED"
    assert c["verdict"] == "PASS"


def test_coverage_only_component_is_not_a_pass(tmp_path) -> None:
    cov = _coverage({"modules/x.py": (95, 100, 48, 50)})
    c = acs.build_component("modules", "p", cov, tmp_path)  # no mutation artifact
    assert c["strength_class"] == "COVERAGE_ONLY"
    assert c["mutation_score"] is None
    assert c["verified_test_strength"] is None
    assert c["verdict"] == "FAIL"  # visibility != verified strength


def test_zero_valid_mutants_fails_closed(tmp_path) -> None:
    cov = _coverage({"core/y.py": (90, 100, 45, 50)})
    (tmp_path / "mutation.core.json").write_text(
        json.dumps({"tool": "mutmut", "killed": 0, "survived": 0, "valid_mutants": 0})
    )
    c = acs.build_component("core", "p", cov, tmp_path)
    assert c["verdict"] == "FAIL"
    assert c["mutation_score"] is None  # no oracle signal


def test_unmeasured_component_is_a_forbidden_gap(tmp_path) -> None:
    cov = _coverage({"libs/db/retry.py": (1, 1, 0, 0)})
    report = acs.build_report(cov, tmp_path, {"libs": "p", "modules": "p"})
    assert "modules" in report["forbidden_gaps"]  # no files -> UNMEASURED
    assert report["verdict"] == "FAIL"


def test_oracle_gap_over_bound_fails(tmp_path) -> None:
    # branch 95, mutation 60 -> gap 35 > 15 -> FAIL even though coverage is high.
    cov = _coverage({"libs/db/retry.py": (95, 100, 95, 100)})
    (tmp_path / "mutation.libs.json").write_text(
        json.dumps({"tool": "mutmut", "killed": 60, "survived": 40, "valid_mutants": 100})
    )
    c = acs.build_component("libs", "p", cov, tmp_path)
    assert c["oracle_gap"] == 35.0
    assert c["verdict"] == "FAIL"


def test_generated_report_validates_against_schema(tmp_path) -> None:
    cov = _coverage({"libs/db/retry.py": (90, 100, 42, 50), "modules/x.py": (80, 100, 40, 50)})
    (tmp_path / "mutation.libs.json").write_text(
        json.dumps({"tool": "mutmut", "killed": 80, "survived": 20, "valid_mutants": 100})
    )
    report = acs.build_report(cov, tmp_path, {"libs": "p", "modules": "p"})
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert report["schema"] == schema["$id"]
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, schema)


def test_mutation_killed_survived_mismatch_fails(tmp_path) -> None:
    # killed + survived (70) != valid_mutants (100): the evidence is unsound.
    cov = _coverage({"libs/db/retry.py": (90, 100, 45, 50)})
    (tmp_path / "mutation.libs.json").write_text(
        json.dumps({"tool": "mutmut", "killed": 50, "survived": 20, "valid_mutants": 100})
    )
    c = acs.build_component("libs", "p", cov, tmp_path)
    assert c["mutation_score"] is None  # rejected, not silently scored
    assert c["strength_class"] == "COVERAGE_ONLY"
    assert c["verdict"] == "FAIL"


# --------------------------------------------------------------------------- #
# Enforcing exit code (Phase-4 I7): a FAIL report must not exit 0.
# --------------------------------------------------------------------------- #
def test_exit_code_pass_is_zero() -> None:
    assert acs.exit_code({"verdict": "PASS"}, report_only=False) == 0


def test_exit_code_fail_is_nonzero_by_default() -> None:
    assert acs.exit_code({"verdict": "FAIL"}, report_only=False) == 1


def test_exit_code_report_only_downgrades_fail_to_zero() -> None:
    assert acs.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def _write_coverage(tmp_path: Path) -> Path:
    # No measured files -> every default component is UNMEASURED -> overall FAIL.
    cov_path = tmp_path / "coverage.json"
    cov_path.write_text(json.dumps({"files": {}}), encoding="utf-8")
    return cov_path


def test_main_fail_verdict_exits_nonzero(tmp_path) -> None:
    cov = _write_coverage(tmp_path)
    out = tmp_path / "report.json"
    rc = acs.main(
        ["--coverage", str(cov), "--mutation-dir", str(tmp_path), "--out", str(out)]
    )
    assert rc == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "FAIL"
    assert report["report_only"] is False


def test_main_report_only_exits_zero_and_marks_artifact(tmp_path) -> None:
    cov = _write_coverage(tmp_path)
    out = tmp_path / "report.json"
    rc = acs.main(
        [
            "--coverage",
            str(cov),
            "--mutation-dir",
            str(tmp_path),
            "--out",
            str(out),
            "--report-only",
        ]
    )
    assert rc == 0  # non-enforcing
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "FAIL"
    assert report["report_only"] is True


def test_report_only_artifact_still_schema_valid(tmp_path) -> None:
    cov = _write_coverage(tmp_path)
    out = tmp_path / "report.json"
    acs.main(
        ["--coverage", str(cov), "--mutation-dir", str(tmp_path), "--out", str(out), "--report-only"]
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, json.loads(SCHEMA.read_text(encoding="utf-8")))
