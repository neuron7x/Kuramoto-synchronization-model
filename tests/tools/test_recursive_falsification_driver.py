# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the WP-07 recursive falsification driver.

The driver is admissibility infrastructure, run on a seeded synthetic statistic;
it makes no predictive claim. The keystone is ``test_loop_can_refute``: the loop
must be able to kill its own hypothesis (a statistic indistinguishable from the
null terminates ``REFUTED``), and ``test_ceiling_is_synthetic`` proves it can
never promote past ``MEASURED_SYNTHETIC`` without real-data evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "recursive_falsification_driver",
        _ROOT / "tools" / "inference" / "recursive_falsification_driver.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_drv = _load()


def test_loop_can_refute() -> None:
    """A statistic pinned at the null centre must terminate REFUTED — the loop
    can falsify its own hypothesis, not only confirm it."""
    ledger = _drv.run_loop(seed=1, observed_statistic=lambda s, i: 0.0)
    assert ledger["terminal_verdict"] == "REFUTED"
    assert ledger["steps"][0]["outcome"] == "REFUTED"
    assert "indistinguishable" in ledger["steps"][0]["cause"]


def test_loop_can_survive_to_bounded_stable() -> None:
    """A clearly extreme statistic survives and terminates BOUNDED_STABLE at the
    synthetic ceiling (never higher)."""
    ledger = _drv.run_loop(seed=2, observed_statistic=lambda s, i: 50.0)
    assert ledger["terminal_verdict"] == "BOUNDED_STABLE"
    assert ledger["claim_tier"] == "MEASURED_SYNTHETIC"


def test_both_terminals_occur_across_seeds() -> None:
    verdicts = {_drv.run_loop(seed=s)["terminal_verdict"] for s in range(40)}
    assert "REFUTED" in verdicts
    assert "BOUNDED_STABLE" in verdicts


def test_ceiling_is_synthetic() -> None:
    for s in range(40):
        ledger = _drv.run_loop(seed=s)
        assert ledger["claim_tier"] in ("UNOBSERVED", "MEASURED_SYNTHETIC")
        assert ledger["claim_ceiling"] == "MEASURED_SYNTHETIC"


def test_never_a_predictive_claim() -> None:
    assert _drv.run_loop(seed=7)["is_predictive_claim"] is False


def test_deterministic_ledger_hash() -> None:
    assert _drv.run_loop(seed=7)["ledger_sha256"] == _drv.run_loop(seed=7)["ledger_sha256"]


def test_every_step_is_an_allowed_outcome() -> None:
    allowed = {"REPRODUCED", "REFUTED", "NARROWED", "STRICTER_RULE", "PROMOTED"}
    for s in range(20):
        for step in _drv.run_loop(seed=s)["steps"]:
            assert step["outcome"] in allowed


def test_main_runs() -> None:
    assert _drv.main(["--seed", "3"]) == 0
