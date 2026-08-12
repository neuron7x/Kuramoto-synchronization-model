# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/governance/replay_release_ledger.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tools.governance.replay_release_ledger import (
    ReplayStatus,
    replay_manifest,
)


def _runner_pass_all(_: str) -> int:
    return 0


def _runner_fail_x(cmd: str) -> int:
    return 1 if "tests/x" in cmd else 0


def _runner_exit2_x(cmd: str) -> int:
    return 2 if "tests/x" in cmd else 0


def _good_manifest(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "main_sha": "deadbeef",
        "pr_list": [1, 2],
        "validators": ["python validators.py"],
        "test_commands": ["pytest tests/x", "pytest tests/y"],
        "expected_exits": {},
        "known_exceptions": [],
    }
    base.update(overrides)
    return base


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_all_commands_pass_yields_replay_pass(tmp_path: Path) -> None:
    manifest = _write(tmp_path / "m.yaml", _good_manifest())
    report = replay_manifest(manifest, runner=_runner_pass_all)
    assert report.status is ReplayStatus.REPLAY_PASS
    assert report.pass_count == 3
    assert report.fail_count == 0


def test_unexpected_failure_yields_replay_fail(tmp_path: Path) -> None:
    """One command exits unexpectedly → REPLAY_FAIL.

    This is the test the falsifier must break.
    """
    manifest = _write(tmp_path / "m.yaml", _good_manifest())
    report = replay_manifest(manifest, runner=_runner_fail_x)
    assert report.status is ReplayStatus.REPLAY_FAIL
    assert report.fail_count == 1


def test_known_exception_downgrades_to_partial(tmp_path: Path) -> None:
    manifest = _write(
        tmp_path / "m.yaml",
        _good_manifest(known_exceptions=["pytest tests/x"]),
    )
    report = replay_manifest(manifest, runner=_runner_fail_x)
    assert report.status is ReplayStatus.REPLAY_PARTIAL
    assert report.excepted_count == 1
    assert report.fail_count == 0


def test_expected_exit_nonzero_treated_as_match(tmp_path: Path) -> None:
    manifest = _write(
        tmp_path / "m.yaml",
        _good_manifest(expected_exits={"pytest tests/x": 2}),
    )
    report = replay_manifest(manifest, runner=_runner_exit2_x)
    assert report.status is ReplayStatus.REPLAY_PASS


def test_missing_manifest_returns_fail_with_error(tmp_path: Path) -> None:
    report = replay_manifest(tmp_path / "absent.yaml", runner=_runner_pass_all)
    assert report.status is ReplayStatus.REPLAY_FAIL
    assert any("not found" in e for e in report.errors)


def test_bad_schema_version_rejected(tmp_path: Path) -> None:
    manifest = _write(tmp_path / "m.yaml", _good_manifest(schema_version=99))
    report = replay_manifest(manifest, runner=_runner_pass_all)
    assert report.status is ReplayStatus.REPLAY_FAIL
    assert any("schema_version" in e for e in report.errors)


def test_missing_required_key_rejected(tmp_path: Path) -> None:
    bad = _good_manifest()
    del bad["validators"]
    manifest = _write(tmp_path / "m.yaml", bad)
    report = replay_manifest(manifest, runner=_runner_pass_all)
    assert report.status is ReplayStatus.REPLAY_FAIL
    assert any("validators" in e for e in report.errors)


def test_empty_command_string_rejected(tmp_path: Path) -> None:
    manifest = _write(
        tmp_path / "m.yaml",
        _good_manifest(test_commands=["pytest tests/x", ""]),
    )
    report = replay_manifest(manifest, runner=_runner_pass_all)
    assert report.status is ReplayStatus.REPLAY_FAIL


def test_falsifier_removing_required_command_breaks_replay(tmp_path: Path) -> None:
    """Remove a required command from the manifest → replay no longer covers it.

    Demonstrates the contract: replay can only attest to what the
    manifest enumerates; an empty manifest means no claim.
    """
    manifest = _write(tmp_path / "m.yaml", _good_manifest(validators=[], test_commands=[]))
    report = replay_manifest(manifest, runner=_runner_pass_all)
    # No commands ran; report is technically PASS (0 fail) but covers
    # nothing — that's the falsifier signal: a manifest with no
    # commands proves nothing.
    assert report.command_count == 0
    assert report.status is ReplayStatus.REPLAY_PASS


def test_replay_manifest_2026_04_27_loads_cleanly() -> None:
    """The shipping replay manifest parses and required keys are present."""
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "docs" / "releases" / "replay_manifest_2026_04_27.yaml"
    assert manifest_path.exists(), f"shipping manifest absent at {manifest_path}"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["main_sha"] == "bb381a8"
    assert isinstance(data["pr_list"], list) and len(data["pr_list"]) >= 20
    assert isinstance(data["validators"], list) and data["validators"]
    assert isinstance(data["test_commands"], list) and data["test_commands"]
