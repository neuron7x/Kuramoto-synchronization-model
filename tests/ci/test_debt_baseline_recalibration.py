# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification battery for the debt-baseline meta-gate recalibration rule.

The meta-gate normally fails on any baseline-total growth. The recalibration
carve-out must let a growth land ONLY when the diff is a pure measurement
change (detector/manifest) with no runtime-code edit — and must NEVER let a
runtime debt growth or a laundering attempt through. These tests pin exactly
that boundary on the pure decision function.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_debt_baseline_monotonic.py"
_spec = importlib.util.spec_from_file_location("check_debt_baseline_monotonic", _MOD_PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ROOTS = ["geosync", "execution", "application", "runtime", "core", "coherence_bridge", "physics_contracts"]
_allowed = _mod._recalibration_allowed


def test_detector_only_change_is_recalibration() -> None:
    # detector improved, no runtime code touched -> growth allowed
    changed = ["scripts/ci/check_code_hygiene.py", "docs/CODE_DEBT_BASELINE.json"]
    assert _allowed(changed, ROOTS) is True


def test_manifest_scope_change_is_recalibration() -> None:
    changed = ["docs/CODE_QUALITY_MANIFEST.json", "docs/CODE_DEBT_BASELINE.json"]
    assert _allowed(changed, ROOTS) is True


def test_runtime_code_growth_is_not_recalibration() -> None:
    # the laundering attack: add debt in runtime code + re-baseline -> blocked
    changed = ["core/foo.py", "docs/CODE_DEBT_BASELINE.json"]
    assert _allowed(changed, ROOTS) is False


def test_mixed_detector_and_runtime_is_blocked() -> None:
    # cannot recalibrate AND edit runtime code in the same PR
    changed = [
        "scripts/ci/check_code_hygiene.py",
        "core/foo.py",
        "docs/CODE_DEBT_BASELINE.json",
    ]
    assert _allowed(changed, ROOTS) is False


def test_baseline_only_growth_is_not_recalibration() -> None:
    # bare --write with no detector/manifest change is never a recalibration
    changed = ["docs/CODE_DEBT_BASELINE.json"]
    assert _allowed(changed, ROOTS) is False


def test_runtime_test_file_does_not_count_as_runtime_code() -> None:
    # a test under a runtime root is not runtime code; detector change still recalibrates
    changed = [
        "scripts/ci/check_code_hygiene.py",
        "core/neuro/tests/test_x.py",
        "docs/CODE_DEBT_BASELINE.json",
    ]
    assert _allowed(changed, ROOTS) is True
