# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Semgrep security scanning workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "semgrep.yml"
pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), reason="workflow file not found")


def _load_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("semgrep workflow should deserialize into a mapping")
    return loaded


def test_workflow_runs_on_push_and_pull_request() -> None:
    """Verify workflow triggers on push and schedule.

    Note: pull_request trigger was intentionally removed - security-policy-enforcement.yml
    provides comprehensive security scanning for PRs to reduce CI overhead.
    """
    workflow = _load_workflow()
    # 'on' is a YAML keyword that becomes True when parsed
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None
    assert "push" in on_config
    # PRs disabled - security-policy-enforcement.yml handles PR security scanning
    # assert "pull_request" in on_config  # Removed intentionally per workflow comment
    assert "schedule" in on_config


def test_workflow_runs_weekly_scan() -> None:
    """Verify weekly scheduled scan is configured."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    schedule = on_config["schedule"]
    assert isinstance(schedule, list)
    assert len(schedule) >= 1
    # Monday at 00:00 UTC
    assert schedule[0]["cron"] == "0 0 * * 1"


def test_semgrep_job_has_security_permissions() -> None:
    """Ensure workflow has permissions to write security events.

    Note: Permissions are defined at workflow level (not job level) for this workflow.
    """
    workflow = _load_workflow()

    # Check workflow-level permissions first
    workflow_permissions = workflow.get("permissions")
    if isinstance(workflow_permissions, dict):
        assert workflow_permissions.get("contents") == "read"
        assert workflow_permissions.get("security-events") == "write"
        return

    # Fall back to job-level permissions if workflow-level not present
    job = workflow["jobs"]["semgrep"]
    permissions = job.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions["contents"] == "read"
    assert permissions["security-events"] == "write"


def test_semgrep_runs_in_container() -> None:
    """Verify Semgrep runs in official container image."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]

    container = job.get("container")
    assert isinstance(container, dict)
    assert container["image"] == "semgrep/semgrep"


def test_semgrep_scans_with_auto_config() -> None:
    """Verify Semgrep uses auto config for multi-language support."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]
    steps = job.get("steps", [])

    semgrep_step = None
    for step in steps:
        if isinstance(step, dict) and "Run Semgrep" in step.get("name", ""):
            semgrep_step = step
            break

    assert semgrep_step is not None
    assert "--config auto" in semgrep_step["run"]
    assert "--sarif" in semgrep_step["run"]


def test_semgrep_outputs_sarif_format() -> None:
    """Ensure Semgrep outputs SARIF for GitHub Security integration."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]
    steps = job.get("steps", [])

    semgrep_step = None
    for step in steps:
        if isinstance(step, dict) and "Run Semgrep" in step.get("name", ""):
            semgrep_step = step
            break

    assert semgrep_step is not None
    assert "--sarif" in semgrep_step["run"]
    assert "semgrep-results.sarif" in semgrep_step["run"]


def test_semgrep_uploads_sarif_to_security_tab() -> None:
    """Verify SARIF results are uploaded to GitHub Security."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]
    steps = job.get("steps", [])

    upload_step = None
    for step in steps:
        if isinstance(step, dict) and "upload-sarif" in step.get("uses", ""):
            upload_step = step
            break

    assert upload_step is not None
    assert upload_step.get("if") == "always()"
    with_section = upload_step.get("with", {})
    assert with_section.get("sarif_file") == "semgrep-results.sarif"


def test_semgrep_checks_critical_findings() -> None:
    """Ensure workflow fails on critical/high severity findings."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]
    steps = job.get("steps", [])

    check_step = None
    for step in steps:
        if isinstance(step, dict) and "Check for critical findings" in step.get("name", ""):
            check_step = step
            break

    assert check_step is not None
    assert "CRITICAL_COUNT" in check_step["run"]
    assert "exit 1" in check_step["run"]


def test_semgrep_scans_error_and_warning_severity() -> None:
    """Verify Semgrep scans for ERROR and WARNING severity."""
    workflow = _load_workflow()
    job = workflow["jobs"]["semgrep"]
    steps = job.get("steps", [])

    semgrep_step = None
    for step in steps:
        if isinstance(step, dict) and "Run Semgrep" in step.get("name", ""):
            semgrep_step = step
            break

    assert semgrep_step is not None
    assert "--severity ERROR" in semgrep_step["run"]
    assert "--severity WARNING" in semgrep_step["run"]
