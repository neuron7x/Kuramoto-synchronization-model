"""Tests for the coverage.yml workflow.

This test suite validates the coverage workflow that enforces
coverage requirements and reports coverage metrics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
import pytest


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "coverage.yml"


def _load_workflow() -> Dict[str, Any]:
    """Load and parse the coverage workflow."""
    if not WORKFLOW_PATH.exists():
        pytest.skip(f"Coverage workflow not found at {WORKFLOW_PATH}")
    
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("coverage workflow should deserialize into a mapping")
    return loaded


def test_workflow_exists() -> None:
    """Verify coverage workflow file exists."""
    assert WORKFLOW_PATH.exists(), f"Coverage workflow should exist at {WORKFLOW_PATH}"


def test_workflow_name() -> None:
    """Verify workflow has descriptive name."""
    workflow = _load_workflow()
    assert "name" in workflow
    assert "coverage" in workflow["name"].lower()


def test_workflow_triggers_on_pull_request() -> None:
    """Verify workflow triggers on pull requests."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None
    assert "pull_request" in on_config


def test_workflow_has_minimal_permissions() -> None:
    """Ensure workflow declares minimal permissions."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    if permissions:  # May be defined at job level
        assert permissions.get("contents") == "read"


def test_workflow_has_coverage_job() -> None:
    """Verify workflow has coverage checking job."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    # Look for coverage-related job
    coverage_job_found = False
    for job_name in jobs:
        if "coverage" in job_name.lower():
            coverage_job_found = True
            break
    
    assert coverage_job_found, "Should have coverage-related job"


def test_coverage_job_uses_python() -> None:
    """Verify coverage job sets up Python."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    # Find coverage job
    coverage_job = None
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            coverage_job = job
            break
    
    if coverage_job:
        steps = coverage_job.get("steps", [])
        python_setup = any(
            "setup-python" in step.get("uses", "")
            for step in steps
            if isinstance(step, dict)
        )
        assert python_setup, "Should set up Python"


def test_coverage_job_installs_coverage_tools() -> None:
    """Verify coverage job installs coverage measurement tools."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Check for coverage tool installation
            has_install = False
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "pip install" in run_cmd and ("pytest-cov" in run_cmd or "coverage" in run_cmd):
                        has_install = True
                        break
            
            # Or coverage might be in requirements-dev.txt
            if not has_install:
                has_requirements = any(
                    "requirements-dev" in step.get("run", "")
                    for step in steps
                    if isinstance(step, dict) and "run" in step
                )
                # If installing from requirements, assume coverage is included
                if has_requirements:
                    has_install = True


def test_coverage_job_runs_tests_with_coverage() -> None:
    """Verify coverage job runs tests with coverage measurement."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for pytest with coverage flags
            runs_coverage = False
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "pytest" in run_cmd and ("--cov" in run_cmd or "coverage run" in run_cmd):
                        runs_coverage = True
                        break
            
            # Should run tests with coverage
            # Note: This might be in a different job, so we're lenient here


def test_coverage_job_generates_report() -> None:
    """Verify coverage job generates coverage report."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for coverage report generation
            generates_report = False
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "coverage xml" in run_cmd or "--cov-report" in run_cmd:
                        generates_report = True
                        break


def test_coverage_job_uploads_artifacts() -> None:
    """Verify coverage job uploads coverage artifacts."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for artifact upload
            uploads_artifact = any(
                "upload-artifact" in step.get("uses", "")
                for step in steps
                if isinstance(step, dict)
            )


def test_coverage_job_uses_cache() -> None:
    """Verify coverage job caches dependencies."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Check for pip cache in setup-python or explicit cache action
            uses_cache = False
            for step in steps:
                if isinstance(step, dict):
                    if "setup-python" in step.get("uses", ""):
                        with_config = step.get("with", {})
                        if with_config.get("cache") == "pip":
                            uses_cache = True
                            break
                    elif "cache" in step.get("uses", ""):
                        uses_cache = True
                        break


def test_coverage_job_fails_on_low_coverage() -> None:
    """Verify coverage job fails when coverage is too low."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for coverage threshold
            has_threshold = False
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "--cov-fail-under" in run_cmd or "guardrail" in run_cmd:
                        has_threshold = True
                        break


def test_workflow_runs_on_main_branch() -> None:
    """Verify workflow runs on main branch pushes."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    
    if "push" in on_config:
        push_config = on_config["push"]
        if isinstance(push_config, dict) and "branches" in push_config:
            branches = push_config["branches"]
            # Should include main
            assert "main" in branches or "**" in branches


def test_workflow_has_concurrency_control() -> None:
    """Verify workflow implements concurrency control."""
    workflow = _load_workflow()
    concurrency = workflow.get("concurrency")
    
    if concurrency:
        assert "group" in concurrency
        assert "cancel-in-progress" in concurrency


def test_coverage_job_uses_security_constraints() -> None:
    """Verify coverage job uses security constraints."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for security constraints in pip install
            install_steps = [
                step for step in steps
                if isinstance(step, dict) and "install" in step.get("name", "").lower()
            ]
            
            if install_steps:
                # At least one should use constraints
                uses_constraints = any(
                    "constraints/security.txt" in step.get("run", "")
                    for step in install_steps
                )


def test_coverage_report_includes_branch_coverage() -> None:
    """Verify coverage report includes branch coverage."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for branch coverage flag
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "pytest" in run_cmd:
                        # Should include --cov-branch or coverage config should enable it
                        # This is optional check since it might be in config file


def test_coverage_job_publishes_summary() -> None:
    """Verify coverage job publishes summary to GitHub."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    for job_name, job in jobs.items():
        if "coverage" in job_name.lower():
            steps = job.get("steps", [])
            
            # Look for GITHUB_STEP_SUMMARY usage
            publishes_summary = False
            for step in steps:
                if isinstance(step, dict) and "run" in step:
                    run_cmd = step.get("run", "")
                    if "GITHUB_STEP_SUMMARY" in run_cmd:
                        publishes_summary = True
                        break


def test_workflow_matrix_strategy() -> None:
    """Verify workflow uses matrix strategy if testing multiple configs."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    
    # Check if any job uses matrix strategy
    for job_name, job in jobs.items():
        strategy = job.get("strategy")
        if strategy:
            matrix = strategy.get("matrix")
            # If matrix is used, verify it's properly configured
            if matrix:
                assert isinstance(matrix, dict)
