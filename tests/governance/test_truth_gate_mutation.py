# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guards for the truth-gate mutation harness itself.

The harness must correctly classify a killed mutant, a SURVIVED mutant (the
case that matters — proving it can detect a decorative gate), and a STALE anchor.
Run against a hermetic toy gate in a temp dir so it touches no real repo file.
"""

from __future__ import annotations

from pathlib import Path

from tools.governance.mutate_truth_gates import Mutation, run_one


def _toy_repo(tmp_path: Path) -> Path:
    (tmp_path / "toygate.py").write_text(
        "def is_bad(x: int) -> bool:\n    return x < 0\n", encoding="utf-8"
    )
    (tmp_path / "test_toygate.py").write_text(
        "from toygate import is_bad\n\n\ndef test_catches() -> None:\n    assert is_bad(-1) is True\n",
        encoding="utf-8",
    )
    return tmp_path


def test_harness_reports_killed(tmp_path: Path) -> None:
    repo = _toy_repo(tmp_path)
    m = Mutation(
        id="toy_killed",
        file="toygate.py",
        find="return x < 0",
        replace="return False",  # is_bad(-1) -> False, test asserts True -> fails -> killed
        killing_test="test_toygate.py::test_catches",
        lie="negativity check disabled",
    )
    result = run_one(m, repo)
    assert result.killed is True
    assert result.stale is False
    # file restored
    assert (repo / "toygate.py").read_text() == "def is_bad(x: int) -> bool:\n    return x < 0\n"


def test_harness_detects_survivor(tmp_path: Path) -> None:
    repo = _toy_repo(tmp_path)
    m = Mutation(
        id="toy_survivor",
        file="toygate.py",
        find="return x < 0",
        replace="return x <= 0",  # is_bad(-1) still True -> test still passes -> SURVIVES
        killing_test="test_toygate.py::test_catches",
        lie="off-by-one the test does not exercise",
    )
    result = run_one(m, repo)
    assert result.killed is False
    assert result.stale is False


def test_harness_flags_stale_anchor(tmp_path: Path) -> None:
    repo = _toy_repo(tmp_path)
    m = Mutation(
        id="toy_stale",
        file="toygate.py",
        find="this string is not in the source",
        replace="irrelevant",
        killing_test="test_toygate.py::test_catches",
        lie="anchor no longer present",
    )
    result = run_one(m, repo)
    assert result.stale is True
    assert result.killed is False
