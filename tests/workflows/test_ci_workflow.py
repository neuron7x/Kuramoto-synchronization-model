"""Tests for the ci.yml (coverage) workflow.

This test suite validates the CI coverage workflow that runs test sharding
and aggregates coverage results across multiple parallel jobs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> Dict[str, Any]:
    """Load and parse the CI workflow."""
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("ci workflow should deserialize into a mapping")
    return loaded


def test_workflow_name() -> None:
    """Verify workflow has proper name."""
    workflow = _load_workflow()
    assert "name" in workflow
    assert "coverage" in workflow["name"].lower() or "ci" in workflow["name"].lower()


def test_workflow_triggers_on_pr_and_push() -> None:
    """Verify workflow triggers on PR and push events."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert on_config is not None
    
    assert "pull_request" in on_config
    assert "push" in on_config
    
    # Check push triggers on main
    push_config = on_config["push"]
    if isinstance(push_config, dict) and "branches" in push_config:
        assert "main" in push_config["branches"]


def test_workflow_has_minimal_permissions() -> None:
    """Ensure workflow declares minimal permissions."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions.get("contents") == "read"


def test_workflow_has_concurrency_control() -> None:
    """Verify workflow implements proper concurrency control."""
    workflow = _load_workflow()
    concurrency = workflow.get("concurrency")
    assert concurrency is not None
    assert "group" in concurrency
    assert "cancel-in-progress" in concurrency
    assert concurrency["cancel-in-progress"] is True


def test_test_coverage_job_uses_sharding() -> None:
    """Verify test-coverage job uses matrix sharding."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    strategy = job.get("strategy")
    assert strategy is not None, "Should use matrix strategy"
    
    matrix = strategy.get("matrix")
    assert matrix is not None
    assert "shard" in matrix
    
    # Check shard count
    shards = matrix["shard"]
    assert isinstance(shards, list)
    assert len(shards) >= 2, "Should shard tests across multiple jobs"


def test_test_coverage_job_fail_fast_disabled() -> None:
    """Verify fail-fast is disabled to run all shards."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    strategy = job.get("strategy")
    assert strategy is not None
    
    # fail-fast should be False to ensure all shards run
    fail_fast = strategy.get("fail-fast", True)
    assert fail_fast is False


def test_test_coverage_job_sets_coverage_file_per_shard() -> None:
    """Verify each shard uses unique coverage file."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    env = job.get("env", {})
    coverage_file = env.get("COVERAGE_FILE", "")
    
    # Should use shard number in filename
    assert "${{ matrix.shard }}" in coverage_file


def test_test_coverage_job_installs_dependencies() -> None:
    """Verify job installs required dependencies."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    install_step = None
    for step in steps:
        if isinstance(step, dict) and "install" in step.get("name", "").lower():
            install_step = step
            break
    
    assert install_step is not None
    run_cmd = install_step.get("run", "")
    
    # Should install from requirements files
    assert "requirements.txt" in run_cmd or "pip install" in run_cmd


def test_test_coverage_job_uses_security_constraints() -> None:
    """Verify job uses security constraints for dependencies."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    install_step = None
    for step in steps:
        if isinstance(step, dict) and "install" in step.get("name", "").lower():
            install_step = step
            break
    
    assert install_step is not None
    run_cmd = install_step.get("run", "")
    assert "constraints/security.txt" in run_cmd


def test_test_coverage_job_runs_pytest_with_coverage() -> None:
    """Verify job runs pytest with coverage measurement."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None
    run_cmd = pytest_step.get("run", "")
    
    # Check coverage flags
    assert "--cov=" in run_cmd
    assert "--cov-config=" in run_cmd


def test_test_coverage_job_uses_test_splits() -> None:
    """Verify job uses pytest-split for test distribution."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    pytest_step = None
    for step in steps:
        if isinstance(step, dict) and "pytest" in step.get("run", "").lower():
            pytest_step = step
            break
    
    assert pytest_step is not None
    run_cmd = pytest_step.get("run", "")
    
    # Should use --splits and --group for sharding
    assert "--splits" in run_cmd
    assert "--group" in run_cmd


def test_test_coverage_job_generates_xml_report() -> None:
    """Verify job generates XML coverage report."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    xml_step = None
    for step in steps:
        if isinstance(step, dict) and ("coverage xml" in step.get("run", "").lower() or "xml" in step.get("name", "").lower()):
            xml_step = step
            break
    
    assert xml_step is not None


def test_test_coverage_job_uploads_shard_artifacts() -> None:
    """Verify job uploads coverage artifacts per shard."""
    workflow = _load_workflow()
    job = workflow["jobs"]["test-coverage"]
    
    steps = job.get("steps", [])
    upload_step = None
    for step in steps:
        if isinstance(step, dict) and "upload" in step.get("uses", "").lower():
            upload_step = step
            break
    
    assert upload_step is not None
    
    # Should use shard number in artifact name
    with_config = upload_step.get("with", {})
    artifact_name = with_config.get("name", "")
    assert "${{ matrix.shard }}" in artifact_name


def test_coverage_aggregate_job_depends_on_test_coverage() -> None:
    """Verify aggregate job depends on test-coverage completion."""
    workflow = _load_workflow()
    job = workflow["jobs"]["coverage-aggregate"]
    
    needs = job.get("needs")
    assert needs is not None
    if isinstance(needs, str):
        assert needs == "test-coverage"
    elif isinstance(needs, list):
        assert "test-coverage" in needs


def test_coverage_aggregate_job_downloads_all_artifacts() -> None:
    """Verify aggregate job downloads all shard artifacts."""
    workflow = _load_workflow()
    job = workflow["jobs"]["coverage-aggregate"]
    
    steps = job.get("steps", [])
    download_steps = [
        step for step in steps
        if isinstance(step, dict) and "download" in step.get("uses", "").lower()
    ]
    
    # Should have at least one download step
    assert len(download_steps) > 0


def test_coverage_aggregate_job_combines_coverage() -> None:
    """Verify aggregate job combines coverage from all shards."""
    workflow = _load_workflow()
    job = workflow["jobs"]["coverage-aggregate"]
    
    steps = job.get("steps", [])
    combine_step = None
    for step in steps:
        if isinstance(step, dict) and ("combine" in step.get("name", "").lower() or "coverage combine" in step.get("run", "").lower()):
            combine_step = step
            break
    
    # Should have logic to combine coverage
    has_combine_logic = False
    for step in steps:
        if isinstance(step, dict) and "run" in step:
            run_cmd = step.get("run", "")
            if "coverage combine" in run_cmd or "coverage xml" in run_cmd:
                has_combine_logic = True
                break
    
    assert has_combine_logic


def test_coverage_aggregate_job_enforces_guardrail() -> None:
    """Verify aggregate job enforces coverage guardrail."""
    workflow = _load_workflow()
    job = workflow["jobs"]["coverage-aggregate"]
    
    steps = job.get("steps", [])
    guardrail_step = None
    for step in steps:
        if isinstance(step, dict) and "guardrail" in step.get("name", "").lower():
            guardrail_step = step
            break
    
    assert guardrail_step is not None
    run_cmd = guardrail_step.get("run", "")
    assert "guardrail" in run_cmd


def test_workflow_caches_pip_dependencies() -> None:
    """Verify workflow caches pip dependencies."""
    workflow = _load_workflow()
    
    # Check both jobs for pip cache
    for job_name in ["test-coverage", "coverage-aggregate"]:
        job = workflow["jobs"][job_name]
        steps = job.get("steps", [])
        
        python_setup = None
        for step in steps:
            if isinstance(step, dict) and "setup-python" in step.get("uses", ""):
                python_setup = step
                break
        
        if python_setup:
            with_config = python_setup.get("with", {})
            assert with_config.get("cache") == "pip"


def test_workflow_uses_specific_python_version() -> None:
    """Verify workflow uses specified Python version."""
    workflow = _load_workflow()
    
    for job_name in ["test-coverage", "coverage-aggregate"]:
        job = workflow["jobs"][job_name]
        steps = job.get("steps", [])
        
        python_setup = None
        for step in steps:
            if isinstance(step, dict) and "setup-python" in step.get("uses", ""):
                python_setup = step
                break
        
        if python_setup:
            with_config = python_setup.get("with", {})
            python_version = with_config.get("python-version")
            assert python_version is not None
            # Should be 3.11 or higher
            if isinstance(python_version, str):
                version_num = float(python_version)
                assert version_num >= 3.11


def test_workflow_fetches_full_history() -> None:
    """Verify workflow fetches full git history."""
    workflow = _load_workflow()
    
    for job_name in ["test-coverage", "coverage-aggregate"]:
        job = workflow["jobs"][job_name]
        steps = job.get("steps", [])
        
        checkout_step = None
        for step in steps:
            if isinstance(step, dict) and "checkout" in step.get("uses", "").lower():
                checkout_step = step
                break
        
        if checkout_step:
            with_config = checkout_step.get("with", {})
            fetch_depth = with_config.get("fetch-depth", 1)
            # Should fetch full history (0) or significant depth
            assert fetch_depth == 0 or fetch_depth == "0"


def test_coverage_aggregate_uploads_final_report() -> None:
    """Verify aggregate job uploads final coverage report."""
    workflow = _load_workflow()
    job = workflow["jobs"]["coverage-aggregate"]
    
    steps = job.get("steps", [])
    upload_steps = [
        step for step in steps
        if isinstance(step, dict) and "upload" in step.get("uses", "").lower()
    ]
    
    assert len(upload_steps) > 0, "Should upload final coverage report"
