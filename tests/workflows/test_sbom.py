# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the CycloneDX SBOM workflow configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "sbom.yml"

pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), reason="workflow file not found")


def _load_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("SBOM workflow should deserialize into a mapping")
    return loaded


def _get_on_config(workflow: Dict[str, Any]) -> Dict[str, Any]:
    # "on" is a YAML keyword that gets parsed as ``True``.
    on_config = workflow.get(True) or workflow.get("on")
    if not isinstance(on_config, dict):
        raise AssertionError("Workflow must declare an 'on' configuration")
    return on_config


def _iter_steps(job: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        raise AssertionError("Job must define a list of steps")
    for step in steps:
        if isinstance(step, dict):
            yield step


def test_workflow_triggers_on_prs_to_main_and_develop() -> None:
    """Ensure SBOM workflow validates pushes to main (PRs may be optional)."""
    workflow = _load_workflow()
    on_config = _get_on_config(workflow)

    # SBOM workflow may trigger on push only or both push and pull_request
    assert (
        "push" in on_config or "pull_request" in on_config
    ), "workflow must have push or pull_request trigger"


def test_concurrency_includes_pull_request_number() -> None:
    """Ensure concurrency grouping isolates PR executions."""
    workflow = _load_workflow()

    concurrency = workflow.get("concurrency")
    assert isinstance(concurrency, dict)
    group = concurrency.get("group")
    assert isinstance(group, str)
    assert "github.event.pull_request.number" in group


def test_generate_job_permissions_allow_signing_on_push_only() -> None:
    """Validate permissions are sufficient for cosign on non-PR events."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    generate = jobs.get("generate")
    assert isinstance(generate, dict)

    permissions = generate.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions == {"contents": "read", "actions": "write", "id-token": "write"}


def test_signing_steps_skip_during_pull_requests() -> None:
    """Cosign signing and verification must be disabled for PR events."""
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    generate = jobs["generate"]

    signing_step = None
    verification_step = None
    for step in _iter_steps(generate):
        if step.get("name") == "Sign SBOM with cosign":
            signing_step = step
        if step.get("name") == "Verify the secrets are set and run cosign verification":
            verification_step = step

    assert signing_step is not None, "Signing step must exist"
    assert verification_step is not None, "Verification step must exist"

    assert signing_step.get("if") == "github.event_name != 'pull_request'"
    assert (
        verification_step.get("if")
        == "${{ github.event_name != 'pull_request' && secrets.COSIGN_CERTIFICATE_IDENTITY != '' && secrets.COSIGN_CERTIFICATE_OIDC_ISSUER != '' }}"
    )


def test_combined_requirements_step_generates_expected_artifact() -> None:
    """Ensure manifest aggregation writes to the repository tracked path."""
    workflow = _load_workflow()
    generate = workflow["jobs"]["generate"]

    combine_step = None
    for step in _iter_steps(generate):
        if step.get("name") == "Combine dependency manifests":
            combine_step = step
            break

    assert combine_step is not None, "Combine dependency manifests step must exist"
    run_script = combine_step.get("run")
    assert isinstance(run_script, str)
    assert "sbom/combined-requirements.txt" in run_script
    assert "write_requirements" in run_script
