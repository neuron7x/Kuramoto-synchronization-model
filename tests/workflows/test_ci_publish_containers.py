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
    if not isinstance(loaded, dict):  # pragma: no cover - defensive, should never happen.
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
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    assert job["needs"] == "coverage-aggregate"


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
    steps = job.get("steps")
    assert isinstance(steps, list)

    def _step_uses(action: str) -> bool:
        return any(
            isinstance(step, dict)
            and step.get("uses", "").startswith(action)
            for step in steps
        )

    assert _step_uses("actions/checkout@")
    assert _step_uses("docker/setup-qemu-action@v3")
    assert _step_uses("docker/setup-buildx-action@v3")
    assert _step_uses("docker/login-action@v3")
    assert _step_uses("docker/metadata-action@v5")
    assert _step_uses("docker/build-push-action@v5")


def test_build_and_push_step_pushes_multi_arch_images() -> None:
    workflow = _load_ci_workflow()
    job = _get_publish_job(workflow)
    steps: List[Dict[str, Any]] = job["steps"]  # type: ignore[assignment]

    build_steps = [
        step for step in steps if isinstance(step, dict) and step.get("uses") == "docker/build-push-action@v5"
    ]
    assert build_steps, "Expected docker/build-push-action@v5 step"
    build_step = build_steps[0]
    with_section = build_step.get("with")
    assert isinstance(with_section, dict)
    assert with_section["push"] is True
    assert with_section["platforms"] == "linux/amd64,linux/arm64"
    assert "${{ steps.meta.outputs.tags }}" in with_section["tags"]
