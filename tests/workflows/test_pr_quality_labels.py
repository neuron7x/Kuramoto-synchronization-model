"""Tests for pr-quality-labels workflow.

This test suite validates the PR quality labels workflow that automatically
applies labels based on PR content and test coverage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-quality-labels.yml"


def _load_workflow() -> Dict[str, Any]:
    """Load and parse the PR quality labels workflow."""
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("pr-quality-labels workflow should deserialize into a mapping")
    return loaded


def test_workflow_triggers_on_pull_request_events() -> None:
    """Verify workflow triggers on correct PR events."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None, "Workflow must have 'on' trigger configuration"
    assert "pull_request_target" in on_config
    
    pr_types = on_config["pull_request_target"]["types"]
    expected_types = ["opened", "reopened", "synchronize", "ready_for_review"]
    assert set(pr_types) == set(expected_types), f"Expected {expected_types}, got {pr_types}"


def test_workflow_has_correct_permissions() -> None:
    """Ensure workflow has proper permissions for PR operations."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    assert isinstance(permissions, dict), "Workflow must declare permissions"
    assert permissions.get("contents") == "read", "Should have read access to contents"
    assert permissions.get("pull-requests") == "write", "Should have write access to PRs"


def test_ensure_labels_job_creates_required_labels() -> None:
    """Verify job creates test-needed and missing-coverage labels."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None, "Must have github-script step"
    script = script_step.get("with", {}).get("script", "")
    
    # Check for label definitions
    assert "test-needed" in script, "Should define test-needed label"
    assert "missing-coverage" in script, "Should define missing-coverage label"
    
    # Check label properties
    assert "b60205" in script or "d93f0b" in script, "Should define label colors"
    assert "description" in script, "Should provide label descriptions"


def test_ensure_labels_job_checks_for_test_files() -> None:
    """Verify job identifies test files in PR changes."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    script = script_step.get("with", {}).get("script", "")
    
    # Check for test file patterns
    assert "testFileMatchers" in script or "test" in script.lower()
    assert "tests/" in script or r"^tests?\/" in script
    assert "/__tests__/" in script or "__tests__" in script


def test_ensure_labels_job_applies_labels_conditionally() -> None:
    """Verify job applies labels based on PR content."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    script = script_step.get("with", {}).get("script", "")
    
    # Check for label application logic
    assert "addLabels" in script, "Should have logic to add labels"
    assert "removeLabel" in script, "Should have logic to remove labels"
    assert "touchesTests" in script or "test" in script.lower(), "Should check for test changes"


def test_ensure_labels_job_only_runs_for_same_repo() -> None:
    """Ensure job only runs for PRs from the same repository (not forks)."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    job_if = job.get("if")
    assert job_if is not None, "Job must have conditional execution"
    assert "github.event.pull_request.head.repo.full_name" in job_if
    assert "github.repository" in job_if
    assert "==" in job_if


def test_ensure_labels_job_handles_pagination() -> None:
    """Verify job handles paginated API responses."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    script = script_step.get("with", {}).get("script", "")
    
    # Check for pagination
    assert "paginate" in script, "Should handle paginated responses"
    assert "per_page" in script, "Should specify items per page"


def test_label_definitions_include_proper_metadata() -> None:
    """Verify label definitions have all required metadata."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    script = script_step.get("with", {}).get("script", "")
    
    # Check that label definitions include required fields
    assert "'name'" in script or '"name"' in script
    assert "'color'" in script or '"color"' in script
    assert "'description'" in script or '"description"' in script


def test_workflow_uses_latest_github_script_action() -> None:
    """Ensure workflow uses a recent version of github-script action."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    action = script_step["uses"]
    # Check version is v7 or higher
    assert "github-script@v" in action
    version = action.split("@v")[-1]
    major_version = int(version.split(".")[0]) if "." in version else int(version)
    assert major_version >= 7, f"Should use github-script@v7 or higher, got {action}"


def test_workflow_error_handling_for_label_operations() -> None:
    """Verify workflow has error handling for label operations."""
    workflow = _load_workflow()
    job = workflow["jobs"]["ensure-labels"]
    
    steps = job.get("steps", [])
    script_step = None
    for step in steps:
        if isinstance(step, dict) and "uses" in step and "github-script" in step["uses"]:
            script_step = step
            break
    
    assert script_step is not None
    script = script_step.get("with", {}).get("script", "")
    
    # Check for error handling
    assert "catch" in script or "error" in script.lower(), "Should have error handling"
    assert "404" in script, "Should handle 404 errors for missing labels"
