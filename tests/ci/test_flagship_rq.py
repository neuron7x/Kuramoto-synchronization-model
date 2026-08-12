# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The flagship-RQ gate must have teeth (RES-001).

Proves that a complete, preregistered flagship RQ passes (POSITIVE), and that a
RQ missing a required field — ``failure_criteria`` — is rejected with a non-zero
exit (NEGATIVE). A gate that cannot fail on an incomplete preregistration is not
a gate.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from scripts.ci.check_flagship_rq import (
    DEFAULT_RQ_DIR,
    REQUIRED_FIELDS,
    evaluate,
    main,
)


def _clone_rq_dir(dst: Path) -> Path:
    """Copy the committed flagship dir into a writable temp location."""
    rq_dir = dst / "flagship"
    shutil.copytree(DEFAULT_RQ_DIR, rq_dir)
    return rq_dir


# --------------------------------------------------------------------------- #
# POSITIVE                                                                     #
# --------------------------------------------------------------------------- #
def test_committed_flagship_rq_is_complete() -> None:
    """The real committed RQ carries every required field and a quarantine list."""
    verdict = evaluate(DEFAULT_RQ_DIR)
    assert verdict["ok"] is True, verdict["problems"]
    assert verdict["missing_fields"] == []
    assert verdict["quarantine_count"] >= 1


def test_gate_exits_zero_on_committed_rq() -> None:
    """The gate entrypoint returns 0 on the committed flagship RQ."""
    assert main(["--rq-dir", str(DEFAULT_RQ_DIR)]) == 0


def test_all_required_fields_are_enforced() -> None:
    """The eight preregistration fields are the ones the gate demands."""
    assert set(REQUIRED_FIELDS) == {
        "estimand",
        "population",
        "intervention",
        "comparator",
        "outcome",
        "constraints",
        "success_criteria",
        "failure_criteria",
    }


# --------------------------------------------------------------------------- #
# NEGATIVE                                                                     #
# --------------------------------------------------------------------------- #
def test_missing_failure_criteria_is_rejected(tmp_path: Path) -> None:
    """Dropping failure_criteria from rq.yaml makes the gate exit non-zero."""
    rq_dir = _clone_rq_dir(tmp_path)
    rq_yaml_path = rq_dir / "rq.yaml"
    data = yaml.safe_load(rq_yaml_path.read_text(encoding="utf-8"))
    del data["failure_criteria"]
    rq_yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    verdict = evaluate(rq_dir)
    assert verdict["ok"] is False
    assert "failure_criteria" in verdict["missing_fields"]
    assert main(["--rq-dir", str(rq_dir)]) == 1


def test_empty_quarantine_is_rejected(tmp_path: Path) -> None:
    """An empty quarantine list is a hard failure (single-flagship must park the rest)."""
    rq_dir = _clone_rq_dir(tmp_path)
    q_path = rq_dir / "quarantine.yaml"
    data = yaml.safe_load(q_path.read_text(encoding="utf-8"))
    data["quarantined"] = []
    q_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert main(["--rq-dir", str(rq_dir)]) == 1


def test_missing_file_is_fail_closed(tmp_path: Path) -> None:
    """A missing rq.yaml is malformed input → exit code 2, never a silent pass."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["--rq-dir", str(empty)]) == 2
