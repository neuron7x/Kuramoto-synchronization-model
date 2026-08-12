# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression for verdict_dag `check` locked-anchor verification.

Before the fix, ``_cmd_check`` never verified ``LOCKED_GOVERNANCE_SHAS``, so a
tampered or missing pinned governance anchor still printed PASS (return 0). The
fix must return 2 on any hash mismatch or missing anchor, while a clean tree
still returns 0.
"""

from __future__ import annotations

import argparse

import pytest

import tools.governance.verdict_dag as vd


def _args() -> argparse.Namespace:
    return argparse.Namespace(verbose=False)


def test_clean_tree_check_passes() -> None:
    assert vd._cmd_check(_args()) == 0


def test_tampered_anchor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real anchor pinned to a WRONG sha simulates on-disk tampering.
    real_rel = next(iter(vd.LOCKED_GOVERNANCE_SHAS))
    monkeypatch.setattr(
        vd,
        "LOCKED_GOVERNANCE_SHAS",
        {real_rel: "0" * 64},
    )
    assert vd._cmd_check(_args()) == 2


def test_missing_anchor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vd,
        "LOCKED_GOVERNANCE_SHAS",
        {"docs/governance/__does_not_exist_xyz__.yaml": "0" * 64},
    )
    assert vd._cmd_check(_args()) == 2
