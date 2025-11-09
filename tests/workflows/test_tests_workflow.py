"""Tests for the main tests.yml workflow.

This test suite validates the primary test workflow that runs on every PR,
ensuring comprehensive coverage, proper CI/CD integration, and quality gates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "tests.yml"


def _load_workflow() -> Dict[str, Any]:
    """Load and parse the tests workflow."""
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("tests workflow should deserialize into a mapping")
    return loaded


def test_workflow_triggers_on_push_and_pull_request() -> None:
    """Verify workflow triggers on push and PR events."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None, "Workflow must have 'on' trigger configuration"
    
    assert "push" in on_config
    assert "pull_request" in on_config
    
    # Check push branches
    push_branches = on_config["push"]["branches"]
    assert "main" in push_branches
    assert "develop" in push_branches


def test_workflow_ignores_documentation_changes() -> None:
    """Verify workflow skips execution for documentation-only changes."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    
    # Check paths-ignore in both push and pull_request
    for trigger in ["push", "pull_request"]:
        if trigger in on_config:
            paths_ignore = on_config[trigger].get("paths-ignore", [])
            assert "**.md" in paths_ignore, f"Should ignore markdown files in {trigger}"
            assert "docs/**" in paths_ignore, f"Should ignore docs directory in {trigger}"


def test_workflow_has_proper_permissions() -> None:
    """Ensure workflow has minimal required permissions."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    assert isinstance(permissions, dict), "Workflow must declare permissions"
    assert permissions.get("contents") == "read"
    assert permissions.get("pull-requests") == "write"


def test_workflow_has_concurrency_control() -> None:
    """Verify workflow implements concurrency control."""
    workflow = _load_workflow()
    concurrency = workflow.get("concurrency")
    assert concurrency is not None, "Workflow must have concurrency control"
    assert "group" in concurrency
    assert "cancel-in-progress" in concurrency
    assert concurrency["cancel-in-progress"] is True


def test_lint_job_runs_static_analysis() -> None:
    """Verify lint job runs all required static analysis tools."""
    workflow = _load_workflow()
    lint_job = workflow["jobs"]["lint"]
    
    steps = lint_job.get("steps", [])
    step_names = [step.get("name", "") for step in steps if isinstance(step, dict)]
    
    # Check for required linting steps
    assert any("ruff" in name.lower() for name in step_names), "Should run ruff"
    assert any("black" in name.lower() for name in step_names), "Should run black"
    assert any("mypy" in name.lower() for name in step_names), "Should run mypy"


def test_lint_job_validates_localization() -> None:
    """Verify lint job validates localization bundles."""
    workflow = _load_workflow()
    lint_job = workflow["jobs"]["lint"]
    
    steps = lint_job.get("steps", [])
    localization_step = None
    for step in steps:
        if isinstance(step, dict) and "localization" in step.get("name", "").lower():
            localization_step = step
            break
    
    assert localization_step is not None, "Should validate localization"


def test_lint_job_runs_secret_detection() -> None:
    """Verify lint job runs detect-secrets scan."""
    workflow = _load_workflow()
    lint_job = workflow["jobs"]["lint"]
    
    steps = lint_job.get("steps", [])
    secret_step = None
    for step in steps:
        if isinstance(step, dict) and "detect-secrets" in step.get("name", "").lower():
            secret_step = step
            break
    
    assert secret_step is not None, "Should run detect-secrets scan"
    assert "detect-secrets" in secret_step.get("run", "")


def test_tests_job_runs_go_tests() -> None:
    """Verify tests job runs Go service unit tests."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    go_step = None
    for step in steps:
        if isinstance(step, dict) and "go test" in step.get("name", "").lower():
            go_step = step
            break
    
    assert go_step is not None, "Should run Go tests"
    assert "go test" in go_step.get("run", "")
    assert "coverage" in go_step.get("run", "").lower()


def test_tests_job_runs_terraform_validation() -> None:
    """Verify tests job validates Terraform configurations."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    terraform_step = None
    for step in steps:
        if isinstance(step, dict) and "terraform" in step.get("name", "").lower():
            terraform_step = step
            break
    
    assert terraform_step is not None, "Should validate Terraform"


def test_tests_job_runs_python_tests_with_coverage() -> None:
    """Verify tests job runs Python tests with coverage requirements."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None, "Should run pytest"
    run_cmd = pytest_step.get("run", "")
    
    # Check coverage flags
    assert "--cov=" in run_cmd, "Should measure coverage"
    assert "--cov-branch" in run_cmd, "Should measure branch coverage"
    assert "--cov-fail-under=" in run_cmd, "Should enforce coverage threshold"
    
    # Check for coverage threshold
    if "--cov-fail-under=" in run_cmd:
        # Extract threshold value
        threshold_part = run_cmd.split("--cov-fail-under=")[1].split()[0]
        threshold = int(threshold_part)
        assert threshold >= 90, f"Coverage threshold should be at least 90%, got {threshold}%"


def test_tests_job_excludes_flaky_tests() -> None:
    """Verify tests job excludes flaky tests from main run."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None
    run_cmd = pytest_step.get("run", "")
    assert '-m "not flaky"' in run_cmd or "-m 'not flaky'" in run_cmd


def test_tests_job_generates_coverage_reports() -> None:
    """Verify tests job generates multiple coverage report formats."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None
    run_cmd = pytest_step.get("run", "")
    
    # Check for various report formats
    assert "--cov-report=xml" in run_cmd, "Should generate XML coverage report"
    assert "--cov-report=term-missing" in run_cmd, "Should show missing lines"
    assert "--cov-report=html" in run_cmd, "Should generate HTML coverage report"


def test_tests_job_generates_junit_xml() -> None:
    """Verify tests job generates JUnit XML for test results."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None
    run_cmd = pytest_step.get("run", "")
    assert "--junitxml=" in run_cmd, "Should generate JUnit XML"


def test_tests_job_runs_e2e_smoke_tests() -> None:
    """Verify tests job runs end-to-end smoke tests."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    e2e_step = None
    for step in steps:
        if isinstance(step, dict) and "e2e" in step.get("name", "").lower():
            e2e_step = step
            break
    
    assert e2e_step is not None, "Should run E2E tests"
    run_cmd = e2e_step.get("run", "")
    assert "tests/e2e/" in run_cmd


def test_tests_job_publishes_coverage_summary() -> None:
    """Verify tests job publishes coverage summary to GitHub."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    summary_step = None
    for step in steps:
        if isinstance(step, dict) and "coverage" in step.get("name", "").lower() and "summary" in step.get("name", "").lower():
            summary_step = step
            break
    
    assert summary_step is not None, "Should publish coverage summary"
    run_cmd = summary_step.get("run", "")
    assert "GITHUB_STEP_SUMMARY" in run_cmd or "coverage" in run_cmd.lower()


def test_tests_job_uploads_coverage_artifacts() -> None:
    """Verify tests job uploads coverage artifacts."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    upload_steps = [
        step for step in steps
        if isinstance(step, dict) and "upload" in step.get("name", "").lower()
    ]
    
    assert len(upload_steps) > 0, "Should upload artifacts"


def test_tests_job_caches_dependencies() -> None:
    """Verify tests job caches Python dependencies."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    python_setup = None
    for step in steps:
        if isinstance(step, dict) and "setup-python" in step.get("uses", ""):
            python_setup = step
            break
    
    assert python_setup is not None
    assert python_setup.get("with", {}).get("cache") == "pip"


def test_web_lint_job_conditional_on_changes() -> None:
    """Verify web lint job has proper dependency on UI change detection."""
    workflow = _load_workflow()
    
    # Check for detect_ui_changes job
    assert "detect_ui_changes" in workflow["jobs"]
    
    # Check web-lint depends on it
    if "web-lint" in workflow["jobs"]:
        web_lint = workflow["jobs"]["web-lint"]
        needs = web_lint.get("needs")
        assert needs is not None, "web-lint should have dependencies"


def test_tests_job_uses_matrix_strategy() -> None:
    """Verify tests job tests against multiple Python versions."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    strategy = tests_job.get("strategy")
    assert strategy is not None, "Should use matrix strategy"
    
    matrix = strategy.get("matrix")
    assert matrix is not None, "Should define test matrix"
    assert "python-version" in matrix


def test_lint_job_uses_precommit_cache() -> None:
    """Verify lint job caches pre-commit environments."""
    workflow = _load_workflow()
    lint_job = workflow["jobs"]["lint"]
    
    steps = lint_job.get("steps", [])
    cache_steps = [
        step for step in steps
        if isinstance(step, dict) and "cache" in step.get("uses", "").lower()
    ]
    
    # Should have at least one cache step
    assert len(cache_steps) > 0, "Should cache dependencies"


def test_workflow_uses_security_constraints() -> None:
    """Verify workflow uses security constraints for dependency installation."""
    workflow = _load_workflow()
    
    # Check both lint and tests jobs
    for job_name in ["lint", "tests"]:
        job = workflow["jobs"][job_name]
        steps = job.get("steps", [])
        
        install_steps = [
            step for step in steps
            if isinstance(step, dict) and "install" in step.get("name", "").lower() and "run" in step
        ]
        
        # At least one install step should use security constraints
        uses_constraints = any(
            "constraints/security.txt" in step.get("run", "")
            for step in install_steps
        )
        assert uses_constraints, f"{job_name} should use security constraints"


def test_workflow_prepares_report_directories() -> None:
    """Verify workflow creates report directories before running tests."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    report_step = None
    for step in steps:
        if isinstance(step, dict) and "report" in step.get("name", "").lower():
            report_step = step
            break
    
    assert report_step is not None, "Should prepare report directories"
    run_cmd = report_step.get("run", "")
    assert "mkdir" in run_cmd


def test_workflow_syncs_localization_before_tests() -> None:
    """Verify workflow syncs localization resources before running tests."""
    workflow = _load_workflow()
    tests_job = workflow["jobs"]["tests"]
    
    steps = tests_job.get("steps", [])
    localization_sync = None
    for step in steps:
        if isinstance(step, dict) and "sync" in step.get("name", "").lower() and "localization" in step.get("name", "").lower():
            localization_sync = step
            break
    
    assert localization_sync is not None, "Should sync localization"
