from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ARTIFACT = """
artifact_type: system_prompt_contract
id: promptops.shadow.contract
version: 1.0.0
objective: Validate deterministic local shadow cases before provider-backed inference.
references:
  - id: spec
    href: https://example.com/spec
messages:
  - role: system
    content: "Use <ref:spec> as context."
unit_tests:
  - id: smoke
    input: "hello"
    assertions:
      - "must produce structured output"
shadow_tests:
  - id: missing-ref-case
    input: "Validate an artifact with a missing referenced id."
    baseline_expectations:
      must_fail: true
      expected_issue: missing_reference_declaration
    quality_gates:
      - "no secret leakage"
      - "deterministic issue code emitted"
  - id: clean-case
    input: "Validate a clean contract."
    baseline_expectations:
      must_fail: false
      forbidden_issue: secret_like_value
    quality_gates:
      - "no secret leakage"
      - "latency budget recorded"
"""


def run_shadow(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/promptops_shadow_runner.py", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_shadow_runner_passes_declared_cases(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.yaml"
    artifact.write_text(ARTIFACT, encoding="utf-8")
    result = run_shadow(artifact)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "local-mock"
    assert payload["summary"]["case_count"] == 2
    assert payload["summary"]["pass_rate"] == 1.0


def test_shadow_runner_writes_report(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.yaml"
    report = tmp_path / "shadow.json"
    artifact.write_text(ARTIFACT, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/promptops_shadow_runner.py", str(artifact), "--report", str(report)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["failed_cases"] == 0


def test_shadow_runner_blocks_unmet_expected_issue(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.yaml"
    artifact.write_text(ARTIFACT.replace("missing referenced id", "complete prompt"), encoding="utf-8")
    result = run_shadow(artifact)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["summary"]["failed_cases"] == 1
    assert any("was not emitted" in note or "expected failure" in note for note in payload["cases"][0]["notes"])
