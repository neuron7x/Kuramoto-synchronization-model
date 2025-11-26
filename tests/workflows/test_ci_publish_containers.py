"""Regression tests for the CI workflow's container publication job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _load_ci_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(
        loaded, dict
    ):  # pragma: no cover - defensive, should never happen.
        raise TypeError("CI workflow should deserialize into a mapping")
    return loaded


def _get_publish_job(loaded: Dict[str, Any]) -> Dict[str, Any]:
    jobs = loaded.get("jobs")
    if not isinstance(jobs, dict):
        raise AssertionError("CI workflow must contain a jobs mapping")
    job = jobs.get("publish-containers")
    if not isinstance(job, dict):
        raise AssertionError("publish-containers job must be defined in CI workflow")
    return job


def _get_step(job: Dict[str, Any], *, uses: str) -> Dict[str, Any]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise AssertionError("publish-containers job must define a steps list")

    matching = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("uses", "").startswith(uses)
    ]
    if not matching:
        raise AssertionError(f"Expected a step using {uses!r}")
    return matching[0]


def _get_step_by_id(job: Dict[str, Any], *, step_id: str) -> Dict[str, Any]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise AssertionError("publish-containers job must define a steps list")

    for step in steps:
        if isinstance(step, dict) and step.get("id") == step_id:
            return step
    raise AssertionError(f"Expected a step with id={step_id!r}")


def _validate_registry_image(image: str, expected_registry: str) -> None:
    """Ensure registry image names are constrained to the expected registry."""
    candidate = image if "://" in image else f"https://{image}"
    parsed = urlsplit(candidate)
    if parsed.netloc != expected_registry:
        raise AssertionError(
            f"{expected_registry} image must target {expected_registry!r}, got {parsed.netloc!r}"
        )
    if not parsed.path.strip("/"):
        raise AssertionError("Registry image path must not be empty")


def test_publish_job_runs_only_on_push_events() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    assert job["if"].strip() == "github.event_name == 'push'"


def test_publish_job_depends_on_coverage_aggregate() -> None:
    """Test that publish job depends on coverage-aggregate (and optionally others)."""
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    needs = job["needs"]
    # needs can be a string or a list
    if isinstance(needs, str):
        assert needs == "coverage-aggregate"
    else:
        assert "coverage-aggregate" in needs


def test_publish_job_sets_required_permissions() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    permissions = job.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions == {"contents": "read", "packages": "write"}


def test_publish_job_defines_expected_environment_variables() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    env = job.get("env")
    assert isinstance(env, dict)
    _validate_registry_image(env["GHCR_IMAGE"], "ghcr.io")
    assert env["DOCKERHUB_IMAGE"]  # non-empty placeholder derived from secrets


def test_publish_job_includes_required_steps() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)

    # ensure each mandatory tool appears at least once
    _get_step(job, uses="actions/checkout@")
    _get_step(job, uses="docker/setup-qemu-action@v3")
    _get_step(job, uses="docker/setup-buildx-action@v3")
    _get_step_by_id(job, step_id="image-targets")
    _get_step(job, uses="docker/metadata-action@v5")
    _get_step(job, uses="docker/build-push-action@v5")
    _get_step(job, uses="docker/login-action@v3")


def test_build_and_push_step_pushes_multi_arch_images() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    steps: List[Dict[str, Any]] = job["steps"]  # type: ignore[assignment]

    build_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("uses") == "docker/build-push-action@v5"
    ]
    assert build_steps, "Expected docker/build-push-action@v5 step"
    build_step = build_steps[0]
    with_section = build_step.get("with")
    assert isinstance(with_section, dict)
    assert with_section["push"] is True
    assert with_section["platforms"] == "linux/amd64,linux/arm64"
    assert "${{ steps.meta.outputs.tags }}" in with_section["tags"]
    assert with_section["labels"] == "${{ steps.meta.outputs.labels }}"


def test_metadata_step_targets_expected_images() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    metadata_step = _get_step(job, uses="docker/metadata-action@v5")
    with_section = metadata_step.get("with")
    assert isinstance(with_section, dict)
    assert with_section.get("images") == "${{ steps.image-targets.outputs.list }}"

    tags_raw = with_section.get("tags")
    assert isinstance(tags_raw, str)
    tags = {line.strip() for line in tags_raw.splitlines() if line.strip()}
    assert {"type=ref,event=branch", "type=ref,event=tag", "type=sha"} <= tags


def test_prepare_step_generates_expected_outputs() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    step = _get_step_by_id(job, step_id="image-targets")
    assert step["shell"] == "bash"
    run_script = step["run"]
    assert 'targets=("${GHCR_IMAGE}")' in run_script
    assert 'targets+=("docker.io/${DOCKERHUB_IMAGE}")' in run_script
    assert "GITHUB_OUTPUT" in run_script
