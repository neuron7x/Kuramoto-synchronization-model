#!/usr/bin/env python3
"""One-command verification harness for the BBB-NVU artifact."""

from __future__ import annotations

import argparse
import json
import platform
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
VERIFY_ARTIFACT = REPO / "tmp" / "bbb_nvu_cng_verify_artifact.json"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PYTHON_FILES = [
    ROOT / "src" / "deterministic_engine.py",
    ROOT / "src" / "runtime_boundary.py",
    ROOT / "src" / "audit.py",
    ROOT / "src" / "observability.py",
    ROOT / "src" / "operational_kernel.py",
    ROOT / "scripts" / "adversarial_auditor.py",
    ROOT / "tools" / "traceability.py",
    ROOT / "tools" / "compile_invariants.py",
    ROOT / "tools" / "verify_artifact.py",
]

TEST_FILES = [
    ROOT / "tests" / "test_deterministic_engine.py",
    ROOT / "tests" / "test_invariants.py",
    ROOT / "tests" / "test_adversarial_auditor.py",
    ROOT / "tests" / "test_traceability.py",
    ROOT / "tests" / "test_l1_data_quality_gate.py",
    ROOT / "tests" / "test_runtime_boundary.py",
    ROOT / "tests" / "test_audit_replay.py",
    ROOT / "tests" / "test_observability_incidents.py",
    ROOT / "tests" / "test_operational_kernel.py",
]


def run(command: list[str], checks: dict[str, Any], key: str) -> None:
    """Run a command and record its deterministic status in the report."""
    subprocess.run(command, cwd=REPO, check=True)
    checks[key] = {"status": "passed", "command": command}


def parse_json_artifacts() -> list[str]:
    """Parse all committed JSON contract artifacts and return their repo paths."""
    parsed: list[str] = []
    for path in [
        *sorted((ROOT / "schemas").glob("*.json")),
        *sorted((ROOT / "examples").glob("*.json")),
        ROOT / "tests" / "adversarial_golden_vectors.json",
    ]:
        json.loads(path.read_text(encoding="utf-8"))
        parsed.append(str(path.relative_to(REPO)))
    return parsed


def compile_python() -> list[str]:
    """Compile critical Python modules and return their repo paths."""
    compiled: list[str] = []
    for path in PYTHON_FILES:
        py_compile.compile(str(path), doraise=True)
        compiled.append(str(path.relative_to(REPO)))
    return compiled


def operational_smoke() -> dict[str, Any]:
    """Execute the operational envelope smoke check and return hash material."""
    from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import load_yaml
    from BBB_NVU_Cognitive_Noise_Gate_2026.src.operational_kernel import (
        OperationalKernel,
        verify_operational_envelope,
    )

    rules = load_yaml(ROOT / "config" / "risk_rules.yaml")
    request: dict[str, Any] = {
        "input_doc": {
            "subject_id": "S-SMOKE",
            "critical_data_invalid": False,
            "confidence": 0.74,
            "domain_indices": {"BSI": 42, "NRI": 28, "VML": 62, "GRS": 48, "CNI": 31},
            "degradations": ["sleep_proxy_low_specificity"],
        },
        "source_id": "smoke.json",
    }
    envelope = OperationalKernel(rules, engine_hash="verification-smoke").execute(
        [request],
        created_at="2026-06-03T00:00:00Z",
    )
    assert envelope.outputs[0]["risk"]["risk_state"] == "YELLOW_WATCH"
    assert envelope.manifest["replay_verified"] == [True]
    assert verify_operational_envelope(envelope)
    assert envelope.envelope_hash
    return {
        "status": "passed",
        "envelope_hash": envelope.envelope_hash,
        "risk_state": envelope.outputs[0]["risk"]["risk_state"],
        "run_hash": envelope.outputs[0]["run_hash"],
        "rules_hash": envelope.outputs[0]["rules_hash"],
        "engine_hash": envelope.outputs[0]["engine_hash"],
        "metrics_snapshot_id": envelope.metrics_snapshot["snapshot_id"],
        "incident_count": len(envelope.incidents),
    }


def write_report(report: dict[str, Any]) -> None:
    """Write deterministic JSON verification evidence."""
    VERIFY_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VERIFY_ARTIFACT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the verifier CLI."""
    parser = argparse.ArgumentParser(description="Verify the BBB-NVU artifact.")
    parser.add_argument("--mode", choices=["full"], default="full")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run all bounded verification checks."""
    build_parser().parse_args(argv)
    checks: dict[str, Any] = {}
    report: dict[str, Any] = {
        "artifact_id": "BBB-NVU-CNG-2026",
        "status": "started",
        "python_version": platform.python_version(),
        "checks": checks,
    }

    run([sys.executable, str(ROOT / "tools" / "traceability.py")], checks, "traceability")
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-W",
        "ignore::DeprecationWarning",
        *[str(path) for path in TEST_FILES],
    ]
    run(pytest_command, checks, "pytest")
    checks["py_compile"] = {"status": "passed", "files": compile_python()}
    checks["json_parse"] = {"status": "passed", "files": parse_json_artifacts()}
    checks["operational_smoke"] = operational_smoke()
    run(
        ["git", "diff", "--check", "--", str(ROOT.relative_to(REPO))],
        checks,
        "git_diff_check",
    )
    report["status"] = "passed"
    write_report(cast(dict[str, Any], report))
    print(f"verification ok: {VERIFY_ARTIFACT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
