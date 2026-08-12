# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The final-inference-verdict workflow must be fail-closed.

Release readiness is a computed verdict, not a mood. This gate keeps the workflow
honest: it must run the aggregator, never swallow its exit code (no
continue-on-error, no ``|| true`` on the aggregate step), and upload the verdict
artifact.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "final-inference-verdict.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_text())


def test_workflow_exists_and_parses() -> None:
    assert WORKFLOW.is_file()
    wf = _workflow()
    assert "final-inference-verdict" in wf["jobs"]


def test_workflow_runs_the_aggregator() -> None:
    steps = _workflow()["jobs"]["final-inference-verdict"]["steps"]
    run_blob = "\n".join(str(step.get("run", "")) for step in steps)
    assert "tools/audit_final_inference_verdict.py" in run_blob


def test_workflow_never_swallows_the_verdict() -> None:
    text = _text()
    # No step may downgrade a failure to a pass.
    assert "continue-on-error: true" not in text
    steps = _workflow()["jobs"]["final-inference-verdict"]["steps"]
    for step in steps:
        run = str(step.get("run", ""))
        if "audit_final_inference_verdict.py" in run:
            assert "|| true" not in run and "|| exit 0" not in run
            assert step.get("continue-on-error") is not True


def test_workflow_uploads_the_verdict_artifact() -> None:
    text = _text()
    assert "upload-artifact@" in text
    assert "final_inference_verdict" in text


def test_workflow_is_a_required_check_on_main() -> None:
    wf = _workflow()
    # PyYAML parses the bare `on:` key as boolean True.
    triggers = wf.get("on", wf.get(True, {}))
    assert "pull_request" in triggers and "push" in triggers
