# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Regression guard for the honest-provenance contract (validator check 5).

PR #414 (sha d48bacf3) shipped an enforcing self-check 5; a later validator
rewrite silently regressed it to an unconditional ``print(... PASS)``. For the
intervening commits any invariant could be relabelled ``ANCHORED`` with zero
gate resistance — exactly the fake-precision failure mode the tier system
exists to prevent. These tests pin the restored fail-closed behaviour so the
regression cannot recur unobserved.

NON_PHYSICS: this exercises the validator's metadata contract, not a physical
quantity, so it carries no INV-* physics witness.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[3] / ".claude" / "physics" / "validate_tests.py"
)


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("validate_tests", _VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator() -> Any:
    return _load_validator()


def test_live_registry_is_clean(validator: Any) -> None:
    """The shipped INVARIANTS.yaml must satisfy the contract it declares."""
    reg = validator.load_invariants()
    assert reg, "INVARIANTS.yaml failed to load"
    assert validator.check_provenance(reg) == []


def test_speculative_cannot_hold_authority(validator: Any) -> None:
    """A SPECULATIVE schema may not carry P0/P1 authority (max P2)."""
    reg = {"INV-X": {"id": "INV-X", "provenance": "SPECULATIVE", "priority": "P0"}}
    errors = validator.check_provenance(reg)
    assert len(errors) == 1
    assert "SPECULATIVE" in errors[0] and "P0" in errors[0]


def test_speculative_at_p2_is_admissible(validator: Any) -> None:
    """SPECULATIVE is allowed at its informational ceiling."""
    reg = {"INV-X": {"id": "INV-X", "provenance": "SPECULATIVE", "priority": "P2"}}
    assert validator.check_provenance(reg) == []


def test_free_text_tier_is_rejected(validator: Any) -> None:
    """Only the three discrete tiers are admissible — no fake precision."""
    reg = {"INV-X": {"id": "INV-X", "provenance": "0.82", "priority": "P2"}}
    errors = validator.check_provenance(reg)
    assert len(errors) == 1
    assert "discrete tier" in errors[0]


@pytest.mark.parametrize("tier", ["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"])
def test_discrete_tiers_accepted(validator: Any, tier: str) -> None:
    priority = "P2" if tier == "SPECULATIVE" else "P0"
    reg = {"INV-X": {"id": "INV-X", "provenance": tier, "priority": priority}}
    assert validator.check_provenance(reg) == []


def test_missing_provenance_is_out_of_scope(validator: Any) -> None:
    """Legacy entries with no declared tier are not invented into one."""
    reg = {"INV-X": {"id": "INV-X", "priority": "P0"}}
    assert validator.check_provenance(reg) == []
