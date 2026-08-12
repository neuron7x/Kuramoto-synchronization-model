# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""R3 — adversarial soundness of the Phase-4 aggregator itself.

N4 hardened the apex; this hardens the aggregator below it. An adversary who sets
a substrate artifact's top-level verdict to PASS while an internal row / invariant
/ check / ground / attack is FAIL must not pass: build_verdict re-reads the nested
items (internal consistency) rather than trusting the headline verdict.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "audit_final_inference_verdict.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("afiv_adv", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


afiv = _load_tool()
_SUBSTRATE = [s for s in afiv.INPUTS if s["tier"] == "substrate"]


def _populate(root: Path) -> None:
    for spec in _SUBSTRATE:
        path = root / spec["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": afiv._SCHEMA_IDS[spec["name"]], "verdict": "PASS"}
        path.write_text(json.dumps(payload), encoding="utf-8")


# --- unit level: the consistency predicate ---------------------------------- #
def test_item_passes_recognises_pass_and_fail_forms() -> None:
    assert afiv._item_passes({"verdict": "PASS"}) is True
    assert afiv._item_passes({"verdict": "BOUND"}) is True
    assert afiv._item_passes({"holds": True}) is True
    assert afiv._item_passes({"verdict": "FAIL"}) is False
    assert afiv._item_passes({"passed": False}) is False
    assert afiv._item_passes({"holds": False}) is False
    assert afiv._item_passes({"defeated": False}) is False


def test_internal_consistency_detects_hidden_failure() -> None:
    assert afiv._internally_consistent({"rows": [{"verdict": "PASS"}]}) is True
    assert afiv._internally_consistent({"rows": [{"verdict": "FAIL"}]}) is False
    assert afiv._internally_consistent({"invariants": [{"passed": False}]}) is False
    assert afiv._internally_consistent({"checks": [{"holds": False}]}) is False


# --- integration: the aggregate over a forged substrate --------------------- #
def test_forged_matrix_row_is_caught(tmp_path) -> None:
    _populate(tmp_path)
    target = _SUBSTRATE[2]  # concurrency_matrix
    path = tmp_path / target["path"]
    path.write_text(
        json.dumps(
            {
                "schema": afiv._SCHEMA_IDS[target["name"]],
                "verdict": "PASS",  # forged headline
                "rows": [{"verdict": "PASS"}, {"verdict": "FAIL"}],  # hidden failure
            }
        ),
        encoding="utf-8",
    )
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"
    entry = next(e for e in report["inputs"] if e["name"] == target["name"])
    assert entry["passed"] is False and "inconsistency" in entry["reason"]


def test_forged_invariant_passed_flag_is_caught(tmp_path) -> None:
    _populate(tmp_path)
    target = _SUBSTRATE[5]  # risk_reservation_lifecycle
    path = tmp_path / target["path"]
    path.write_text(
        json.dumps(
            {
                "schema": afiv._SCHEMA_IDS[target["name"]],
                "verdict": "BOUND",
                "invariants": [{"passed": True}, {"passed": False}],
            }
        ),
        encoding="utf-8",
    )
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"


def test_honest_artifacts_with_passing_internals_still_pass(tmp_path) -> None:
    _populate(tmp_path)
    target = _SUBSTRATE[2]
    path = tmp_path / target["path"]
    path.write_text(
        json.dumps(
            {
                "schema": afiv._SCHEMA_IDS[target["name"]],
                "verdict": "PASS",
                "rows": [{"verdict": "PASS"}, {"verdict": "PASS"}],
            }
        ),
        encoding="utf-8",
    )
    assert afiv.build_verdict(tmp_path, release=False)["verdict"] == "PASS"
