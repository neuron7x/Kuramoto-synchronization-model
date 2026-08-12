# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for version-gate workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "version-gate.yml"
pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), reason="workflow file not found")


def _load_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("version-gate workflow should deserialize into a mapping")
    return loaded


def test_workflow_triggers_on_pull_request() -> None:
    """Verify workflow triggers on PRs to main and develop."""
    workflow = _load_workflow()
    # 'on' is a YAML keyword that becomes True when parsed
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None, "Workflow must have 'on' trigger configuration"
    assert "pull_request" in on_config
    assert set(on_config["pull_request"]["branches"]) == {"main", "develop"}


def test_version_check_job_has_minimal_permissions() -> None:
    """Ensure job uses least privilege GITHUB_TOKEN permissions."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    job = jobs.get("version-check")
    assert isinstance(job, dict), "version-check job must be defined"

    permissions = job.get("permissions")
    assert isinstance(permissions, dict), "Job must declare explicit permissions"
    assert permissions == {"contents": "read"}, "Job should have minimal read-only permissions"


def test_version_check_job_installs_setuptools_scm() -> None:
    """Verify setuptools_scm is installed for version checking."""
    workflow = _load_workflow()
    job = workflow["jobs"]["version-check"]
    steps = job.get("steps", [])

    install_step = None
    for step in steps:
        if isinstance(step, dict) and "Install dependencies" in step.get("name", ""):
            install_step = step
            break

    assert install_step is not None, "Install dependencies step must exist"
    assert "setuptools_scm" in install_step["run"]


def test_version_check_compares_scm_version_with_git_tag() -> None:
    """Ensure workflow compares setuptools_scm version with git tags."""
    workflow = _load_workflow()
    job = workflow["jobs"]["version-check"]
    steps = job.get("steps", [])

    # Check for SCM version step
    scm_step = None
    for step in steps:
        if isinstance(step, dict) and step.get("id") == "scm_version":
            scm_step = step
            break

    assert scm_step is not None, "SCM version step must exist"
    assert "python -m setuptools_scm" in scm_step["run"]

    # Check for git tag step
    tag_step = None
    for step in steps:
        if isinstance(step, dict) and step.get("id") == "git_tag":
            tag_step = step
            break

    assert tag_step is not None, "Git tag step must exist"
    assert "git describe --tags --abbrev=0" in tag_step["run"]

    # Check for comparison step
    compare_step = None
    for step in steps:
        if isinstance(step, dict) and "Compare versions" in step.get("name", ""):
            compare_step = step
            break

    assert compare_step is not None, "Compare versions step must exist"
    assert "scm_version" in compare_step["run"]
    assert "git_tag" in compare_step["run"]


def test_version_check_allows_development_versions() -> None:
    """Verify workflow allows development versions with .dev suffix."""
    workflow = _load_workflow()
    job = workflow["jobs"]["version-check"]
    steps = job.get("steps", [])

    compare_step = None
    for step in steps:
        if isinstance(step, dict) and "Compare versions" in step.get("name", ""):
            compare_step = step
            break

    assert compare_step is not None
    assert ".dev" in compare_step["run"]
    assert "Development version detected" in compare_step["run"]


def test_version_check_fails_on_version_mismatch() -> None:
    """Ensure workflow fails when release version doesn't match tag."""
    workflow = _load_workflow()
    job = workflow["jobs"]["version-check"]
    steps = job.get("steps", [])

    compare_step = None
    for step in steps:
        if isinstance(step, dict) and "Compare versions" in step.get("name", ""):
            compare_step = step
            break

    assert compare_step is not None
    assert "exit 1" in compare_step["run"]
    assert "Version mismatch" in compare_step["run"]
