"""Workflow-hygiene gate for the L2 demo CI protection.

Verifies that `.github/workflows/l2-demo-gate.yml` stays:
  · YAML-valid
  · minimum-permission (`contents: read`)
  · concurrency-grouped
  · trigger-path complete (covers every L2-surface path we care about)
  · 40-char-SHA pinned on third-party actions (repo policy)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

_WF = Path(".github/workflows/l2-demo-gate.yml")


@pytest.fixture(scope="module")
def workflow() -> dict[str, object]:
    if not _WF.exists():
        pytest.skip(f"{_WF} not present")
    with _WF.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    return data


def test_yaml_parses_to_dict(workflow: dict[str, object]) -> None:
    assert "jobs" in workflow
    # The top-level "on" key maps to True (bool) when YAML parses "on:" —
    # depending on parser. Just verify the triggers are declared by
    # re-loading with BaseLoader to keep string fidelity.
    with _WF.open("r", encoding="utf-8") as f:
        raw = f.read()
    assert "pull_request:" in raw
    assert "merge_group:" in raw


def test_permissions_is_least_privilege(workflow: dict[str, object]) -> None:
    perms = workflow.get("permissions")
    assert perms == {"contents": "read"}, f"unexpected permissions: {perms}"


def test_concurrency_is_declared(workflow: dict[str, object]) -> None:
    conc = workflow.get("concurrency")
    assert isinstance(conc, dict)
    assert "group" in conc
    assert conc.get("cancel-in-progress") is True


def test_trigger_paths_cover_l2_surface() -> None:
    """Every L2-surface path we need must be declared in the trigger."""
    raw = _WF.read_text(encoding="utf-8")
    required_patterns = [
        "research/microstructure/**",
        "scripts/run_l2_*.py",
        "scripts/render_l2_*.py",
        "tests/test_l2_*.py",
        "tests/l2_artifacts.py",
        "Makefile",
        "README.md",
        "results/gate_fixtures/**",
    ]
    missing = [p for p in required_patterns if p not in raw]
    assert not missing, f"Trigger path missing: {missing}"


def test_third_party_actions_pinned_by_sha(workflow: dict[str, object]) -> None:
    """Every `uses:` reference must pin to a 40-char commit SHA (repo policy)."""
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    for job_name, job in jobs.items():
        assert isinstance(job, dict), job_name
        steps = job.get("steps", [])
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, dict)
            uses = step.get("uses")
            if uses is None:
                continue
            # Extract SHA — must be 40 hex chars after @
            m = re.search(r"@([0-9a-f]{40})\b", str(uses))
            assert (
                m is not None
            ), f"Job '{job_name}' step '{step.get('name')}' uses '{uses}' is not SHA-pinned"


def test_every_job_has_timeout(workflow: dict[str, object]) -> None:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    for job_name, job in jobs.items():
        assert isinstance(job, dict)
        assert "timeout-minutes" in job, f"job '{job_name}' has no timeout"
        assert int(job["timeout-minutes"]) > 0


def test_every_checkout_disables_persist_credentials(workflow: dict[str, object]) -> None:
    """actions/checkout must set persist-credentials: false (credentials hygiene)."""
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    for job in jobs.values():
        assert isinstance(job, dict)
        for step in job.get("steps", []):
            assert isinstance(step, dict)
            if "checkout" in str(step.get("uses", "")):
                with_map = step.get("with", {})
                assert isinstance(with_map, dict)
                assert with_map.get("persist-credentials") is False
