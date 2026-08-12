# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the Terraform pinning workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pin-terraform-version.yml"
)

pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), reason="workflow file not found")


def _load_workflow() -> Dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("Pin Terraform workflow should deserialize into a mapping")
    return loaded


def test_workflow_triggers_for_pull_requests_into_main() -> None:
    """The workflow must validate Terraform changes for PRs targeting main."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert isinstance(on_config, dict)

    pr_config = on_config.get("pull_request")
    assert isinstance(pr_config, dict)
    assert pr_config.get("branches") == ["main"]


def test_concurrency_group_isolated_by_pr_number() -> None:
    """Ensure PR executions do not cancel push runs and vice versa."""
    workflow = _load_workflow()
    concurrency = workflow.get("concurrency")
    assert isinstance(concurrency, dict)
    group = concurrency.get("group")
    assert isinstance(group, str)
    assert "github.event.pull_request.number" in group


def test_workflow_declares_minimal_permissions() -> None:
    """Workflow-level permissions should be read-only plus actions writes for caches."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions == {"contents": "read", "actions": "write"}


def test_job_uses_cached_go_and_fixed_terraform_version() -> None:
    """Terraform validation job must install pinned tool versions."""
    workflow = _load_workflow()
    jobs = workflow.get("jobs", {})
    job = jobs.get("terraform-validate")
    assert isinstance(job, dict)

    steps = job.get("steps", [])
    assert isinstance(steps, list)

    setup_go = None
    setup_tf = None
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("uses") == "actions/setup-go@v5":
            setup_go = step
        if step.get("uses") == "hashicorp/setup-terraform@v3":
            setup_tf = step

    assert setup_go is not None
    with_section = setup_go.get("with")
    assert isinstance(with_section, dict)
    # Accept either go-version or go-version-file
    assert with_section.get("go-version") or with_section.get("go-version-file")
    assert with_section.get("cache") is True
    assert with_section.get("cache-dependency-path") == "infra/terraform/tests/go.sum"

    assert setup_tf is not None
    tf_with = setup_tf.get("with")
    assert isinstance(tf_with, dict)
    assert tf_with.get("terraform_version") == "1.6.6"
