# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The RES-010 power/effect-size/uncertainty gate must have teeth.

POSITIVE: the committed report -- SESOI + effect-size + interval + a power gate,
with the binary verdict honestly withheld (not underpowered, but reproducibility
unverified) -> the gate passes (exit 0).

NEGATIVE 1: a binary SUPPORTED claim while flagged underpowered -> RED.
NEGATIVE 2: a report missing the effect-size / interval -> RED.
NEGATIVE 3: a report missing the power_adequacy gate field -> RED.

The negative tests mutate an in-memory copy of the report; they never touch the
tracked artifact, so they can never leave the tree dirty.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "scripts" / "ci"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_power_uq as gate  # noqa: E402  (scripts/ci/check_power_uq.py)

REPORT_PATH = ROOT / "artifacts" / "research" / "power_uq_report.json"


def _load() -> dict:
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The committed report exists and is well-formed.                              #
# --------------------------------------------------------------------------- #
def test_report_exists_and_is_object() -> None:
    assert REPORT_PATH.exists(), "power_uq_report.json must be committed"
    report = _load()
    assert isinstance(report, dict)


def test_report_declares_sesoi_of_one() -> None:
    """SESOI is the smallest effect of interest = >= 1 genuinely-missed defect."""
    report = _load()
    sesoi = report["sesoi"]
    assert sesoi["value"] == 1
    assert sesoi["direction"] == "at_least"


def test_effect_size_and_interval_are_primary_not_bare_p() -> None:
    """Effect size + interval lead; no bare p-value is the headline."""
    report = _load()
    assert report["effect_size"]["point_estimate"] == 70
    assert report["primary_report"]["bare_p_value"] is None
    assert gate._has_effect_size(report)
    assert gate._has_interval(report)


def test_dependence_and_census_caveats_present() -> None:
    report = _load()
    assert report["dependence_caveat"]["independent_bernoulli_assumption_holds"] is False
    assert report["census_vs_sample"]["is_census"] is True
    assert report["census_vs_sample"]["sampling_uncertainty"] == "none"


# --------------------------------------------------------------------------- #
# POSITIVE: the committed report passes the gate.                              #
# --------------------------------------------------------------------------- #
def test_positive_committed_report_passes() -> None:
    report = _load()
    verdict = gate.evaluate(report)
    assert verdict["ok"], verdict["problems"]
    # Not underpowered, but the binary claim is honestly withheld.
    assert verdict["underpowered"] is False
    assert verdict["binary_claim_present"] is False


def test_gate_main_exit_zero_on_committed_report() -> None:
    assert gate.main([]) == 0


# --------------------------------------------------------------------------- #
# NEGATIVE 1: a binary SUPPORTED claim while underpowered -> RED.              #
# --------------------------------------------------------------------------- #
def test_negative_binary_claim_while_underpowered_is_red() -> None:
    report = copy.deepcopy(_load())
    report["verdict"] = "SUPPORTED"
    report["power_adequacy"]["underpowered"] = True
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("underpowered" in p for p in verdict["problems"])


def test_negative_binary_claim_while_unreproducible_is_red() -> None:
    """Even if NOT underpowered, a binary SUPPORTED while reproducibility is
    unverified is RED (RES-008 consistency guard)."""
    report = copy.deepcopy(_load())
    report["verdict"] = "SUPPORTED"
    report["power_adequacy"]["underpowered"] = False
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("reproducibility" in p for p in verdict["problems"])


# --------------------------------------------------------------------------- #
# NEGATIVE 2: missing effect-size / interval -> RED.                          #
# --------------------------------------------------------------------------- #
def test_negative_missing_effect_size_is_red() -> None:
    report = copy.deepcopy(_load())
    report["effect_size"].pop("point_estimate", None)
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("effect-size" in p for p in verdict["problems"])


def test_negative_missing_interval_is_red() -> None:
    report = copy.deepcopy(_load())
    report["intervals"] = []
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("interval" in p for p in verdict["problems"])


# --------------------------------------------------------------------------- #
# NEGATIVE 3: missing power gate field -> RED.                                 #
# --------------------------------------------------------------------------- #
def test_negative_missing_power_field_is_red() -> None:
    report = copy.deepcopy(_load())
    report.pop("power_adequacy", None)
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("power gate field missing" in p for p in verdict["problems"])


def test_negative_power_block_without_gate_key_is_red() -> None:
    report = copy.deepcopy(_load())
    report["power_adequacy"].pop("power_gate", None)
    verdict = gate.evaluate(report)
    assert not verdict["ok"]
    assert any("power gate field missing" in p for p in verdict["problems"])


# --------------------------------------------------------------------------- #
# NEGATIVE 7 (hardening): self-declared reproducibility cannot exceed the      #
# RES-008 SSOT. A falsified reproducibility flag + binary verdict must go RED. #
# --------------------------------------------------------------------------- #
def test_negative_self_declared_reproducibility_beyond_ssot_is_red() -> None:
    report = copy.deepcopy(_load())
    report.setdefault("reproducibility_caveat", {})["reproducibility_verified_at_S"] = True
    report["verdict"] = "SUPPORTED"
    if isinstance(report.get("power_adequacy"), dict):
        report["power_adequacy"]["underpowered"] = False
    verdict = gate.evaluate(report)
    assert not verdict["ok"], "falsified reproducibility flag must fail closed"
    assert any("source of record" in p or "cannot exceed the SSOT" in p
               for p in verdict["problems"])
