# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The FLAGSHIP-RQ-001 selection-bias gate (RES-007) must have teeth.

POSITIVE: the tracked report -- pre-specified primary + recorded selection_count
+ a valid multiple-testing correction + a non-inflated verdict -> gate passes
(exit 0).

NEGATIVE 1: primary != preregistered primary -> RED.
NEGATIVE 2: missing selection_count -> RED.
NEGATIVE 3: a best-of-N pick presented as primary WITHOUT correction -> RED.
(Plus: an inflated final_verdict -> RED.)

The negative tests mutate an on-disk copy inside a temp dir (never the tracked
report) and monkeypatch the gate's REPORT_PATH, so they can never leave the tree
dirty.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "scripts" / "ci"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_selection_bias as gate  # noqa: E402  (scripts/ci/check_selection_bias.py)


def _tracked_report() -> dict:
    return json.loads(gate.REPORT_PATH.read_text(encoding="utf-8"))


def _install(tmp_path, monkeypatch, report: dict) -> Path:
    broken = tmp_path / "selection_bias_report.json"
    broken.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "REPORT_PATH", broken)
    return broken


# --------------------------------------------------------------------------- #
# Report-content invariants (self-consistency of the tracked artifact).         #
# --------------------------------------------------------------------------- #
def test_tracked_report_is_internally_consistent() -> None:
    report = _tracked_report()
    assert report["selection_count"] == len(report["comparisons"])
    assert report["primary"]["pre_specified"] is True
    # The pre-specified primary must be one of the recorded comparisons.
    names = {c["name"] for c in report["comparisons"]}
    assert report["primary"]["name"] in names


def test_correction_only_rejects_the_pre_specified_primary() -> None:
    """No cherry-pick: exactly the preregistered primary survives correction."""
    report = _tracked_report()
    rejected = report["correction"]["rejected_after_correction"]
    assert rejected == [report["primary"]["name"]]


def test_no_manufactured_significance() -> None:
    """The corrected conclusion stays INSUFFICIENT_EVIDENCE (RES-008)."""
    report = _tracked_report()
    assert report["final_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert report["corrected_conclusion"]["manufactured_significance"] is False


# --------------------------------------------------------------------------- #
# POSITIVE: the tracked report passes the gate.                                  #
# --------------------------------------------------------------------------- #
def test_gate_passes_on_tracked_report() -> None:
    verdict = gate.evaluate()
    assert verdict["ok"], f"gate should pass, got problems: {verdict['problems']}"
    assert gate.main([]) == 0


def test_declared_primary_matches_prereg_primary() -> None:
    verdict = gate.evaluate()
    assert verdict["declared_primary"] == verdict["expected_primary"]
    assert verdict["declared_primary"] == "FLAGSHIP vs EXISTING_SUITE"


# --------------------------------------------------------------------------- #
# NEGATIVE 1: primary != preregistered primary -> RED.                           #
# --------------------------------------------------------------------------- #
def test_gate_fails_when_primary_is_not_prereg_primary(tmp_path, monkeypatch) -> None:
    report = _tracked_report()
    report["primary"]["null_baseline"] = "NAIVE"  # post-hoc null, not the prereg one
    _install(tmp_path, monkeypatch, report)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("does NOT match the preregistered primary" in p for p in verdict["problems"])
    assert gate.main([]) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE 2: missing selection_count -> RED.                                    #
# --------------------------------------------------------------------------- #
def test_gate_fails_when_selection_count_missing(tmp_path, monkeypatch) -> None:
    report = _tracked_report()
    del report["selection_count"]
    _install(tmp_path, monkeypatch, report)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("selection_count is unrecorded" in p for p in verdict["problems"])
    assert gate.main([]) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE 3: best-of-N as primary WITHOUT correction -> RED.                    #
# --------------------------------------------------------------------------- #
def test_gate_fails_on_best_of_n_primary_without_correction(tmp_path, monkeypatch) -> None:
    report = _tracked_report()
    report["primary"]["pre_specified"] = False
    report["primary"]["selection_basis"] = "post_hoc_best_of_n"
    del report["correction"]  # remove the correction record entirely
    _install(tmp_path, monkeypatch, report)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("best-of-N" in p for p in verdict["problems"])
    assert gate.main([]) == 1


def test_gate_flags_inflated_verdict(tmp_path, monkeypatch) -> None:
    """A corrected conclusion inflated past the RES-008 verdict is caught."""
    report = _tracked_report()
    report["final_verdict"] = "SUPPORTED"  # manufacture significance
    _install(tmp_path, monkeypatch, report)

    verdict = gate.evaluate()
    assert not verdict["ok"]
    assert any("does NOT match the RES-008" in p for p in verdict["problems"])
    assert gate.main([]) == 1
