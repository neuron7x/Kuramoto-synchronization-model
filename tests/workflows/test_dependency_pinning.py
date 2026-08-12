# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for dependency-pinning workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dependency-pinning.yml"
)

pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), reason="workflow file not found")


def _load_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("dependency-pinning workflow should deserialize into a mapping")
    return loaded


def test_workflow_triggers_on_dependency_file_changes() -> None:
    """Verify workflow triggers on changes to dependency files."""
    workflow = _load_workflow()
    # 'on' is a YAML keyword that becomes True when parsed
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None
    assert "pull_request" in on_config
    pr_config = on_config["pull_request"]

    assert "paths" in pr_config
    paths = pr_config["paths"]

    # Check for critical dependency files
    assert "requirements*.txt" in paths
    assert "pyproject.toml" in paths
    assert "package.json" in paths
    assert "package-lock.json" in paths
    assert "Cargo.toml" in paths
    assert "Cargo.lock" in paths
    assert "go.mod" in paths
    assert "go.sum" in paths


def test_check_job_has_minimal_permissions() -> None:
    """Ensure job uses least privilege GITHUB_TOKEN permissions."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]

    permissions = job.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions == {"contents": "read"}


def test_check_python_dependencies_validates_lock_files() -> None:
    """Verify Python lock files are checked."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]
    steps = job.get("steps", [])

    python_step = None
    for step in steps:
        if isinstance(step, dict) and "Check Python dependencies" in step.get("name", ""):
            python_step = step
            break

    assert python_step is not None
    assert "requirements.lock" in python_step["run"]
    assert "requirements-dev.lock" in python_step["run"]
    assert "exit 1" in python_step["run"]


def test_check_nodejs_dependencies_validates_package_lock() -> None:
    """Verify Node.js package-lock.json is checked."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]
    steps = job.get("steps", [])

    nodejs_step = None
    for step in steps:
        if isinstance(step, dict) and "Check Node.js dependencies" in step.get("name", ""):
            nodejs_step = step
            break

    assert nodejs_step is not None
    assert "package-lock.json" in nodejs_step["run"]
    assert "hashFiles" in nodejs_step.get("if", "")


def test_check_rust_dependencies_validates_cargo_lock() -> None:
    """Verify Rust Cargo.lock is checked."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]
    steps = job.get("steps", [])

    rust_step = None
    for step in steps:
        if isinstance(step, dict) and "Check Rust dependencies" in step.get("name", ""):
            rust_step = step
            break

    assert rust_step is not None
    assert "Cargo.lock" in rust_step["run"]


def test_check_go_dependencies_validates_go_sum() -> None:
    """Verify Go go.sum is checked."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]
    steps = job.get("steps", [])

    go_step = None
    for step in steps:
        if isinstance(step, dict) and "Check Go dependencies" in step.get("name", ""):
            go_step = step
            break

    assert go_step is not None
    assert "go.sum" in go_step["run"]


def test_workflow_fails_on_missing_lock_files() -> None:
    """Ensure workflow exits with error when lock files are missing."""
    workflow = _load_workflow()
    job = workflow["jobs"]["check-pinned-dependencies"]
    steps = job.get("steps", [])

    # Check that steps have error conditions
    error_checks = 0
    for step in steps:
        if isinstance(step, dict) and "run" in step:
            if "exit 1" in step["run"] and "not found" in step["run"]:
                error_checks += 1

    assert error_checks >= 3, "Should have error checks for multiple ecosystems"
