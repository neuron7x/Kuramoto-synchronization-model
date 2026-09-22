# Copyright (c) 2023-2026 Yaroslav Vasylenko
# SPDX-License-Identifier: MIT
"""D-002L-P0 pre-registration guards.

Pure governance tests: no outcome download, no scoring, no model fit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG = REPO_ROOT / "docs/governance/D002L_PREREGISTRATION.yaml"
RATIONALE = REPO_ROOT / "docs/research/D002L_DESIGN_RATIONALE.md"
FAILURE = REPO_ROOT / "artifacts/d002l/prereg/d002l_failure_axis_inheritance_v1.json"
ESTIMAND = REPO_ROOT / "artifacts/d002l/prereg/d002l_primary_estimand_contract_v1.json"
SOURCE_PLAN = REPO_ROOT / "artifacts/d002l/prereg/d002l_source_plan_v1.json"
VERDICT = REPO_ROOT / "artifacts/governance/verdicts/d002l_p0_verdict_v1.json"
PARENT = REPO_ROOT / "artifacts/governance/verdicts/d002k_p4_verdict_v1.json"
D002J_PREREG = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
D002K_PREREG = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"

D002J_PREREG_SHA256 = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"
D002K_PREREG_SHA256 = "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"


def _yaml() -> dict[str, Any]:
    obj = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)
    return obj


def _json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)
    return obj


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_d002l_files_exist() -> None:
    for path in (PREREG, RATIONALE, FAILURE, ESTIMAND, SOURCE_PLAN, VERDICT):
        assert path.is_file(), path
        assert path.stat().st_size > 0, path


def test_schema_and_fresh_lineage() -> None:
    p = _yaml()
    assert p["schema_version"] == "D002L-PREREG-v1"
    assert p["study_id"] == "D-002L"
    assert p["parent_lineage"] == "D-002K"
    assert p["parent_node"] == "D002K-P4"
    assert p["parent_status"] == "TERMINAL_REFUSED"
    assert p["is_rescue"] is False


def test_parent_is_exact_refusal_class() -> None:
    parent = _json(PARENT)
    assert parent["node_id"] == "D002K-P4"
    assert parent["decision"] == "POWER_GATE_REFUSED_UNDERPOWERED"
    assert parent["status"] == "TERMINAL_REFUSED"
    assert "effect_too_small_event_conditioned" in parent["failure_retention"]


def test_inherited_failure_axis_exact() -> None:
    p = _yaml()
    f = _json(FAILURE)
    assert p["inherited_failure_axis"] == "effect_too_small_event_conditioned"
    assert f["inherited_failure_axis"] == "effect_too_small_event_conditioned"
    assert f["parent_power"]["feasible_n_crisis"] == 1
    assert f["parent_power"]["power"] == 0.0481
    assert f["parent_power"]["n_min_crisis_replicates"] == 20


def test_structural_repair_changes_replication_unit_not_alpha() -> None:
    p = _yaml()
    repair = p["structural_repair"]
    assert repair["old_unit"] == "unique_historical_crisis_window"
    assert repair["new_unit"] == "unique_coupon_settlement_date"
    assert repair["no_pseudoreplication"] is True
    f = _json(FAILURE)["structural_repair"]
    assert f["synthetic_reseeding"] is False
    assert f["statistics_relaxed"] is False


def test_exactly_one_primary_estimand() -> None:
    p = _yaml()
    e = _json(ESTIMAND)
    assert p["primary_estimand"]["id"] == "beta_coupon_settlement"
    assert p["primary_estimand"]["primary_parameter"] == "beta_coupon"
    assert p["primary_estimand"]["exactly_one_confirmatory_parameter"] is True
    assert e["exactly_one_confirmatory_parameter"] is True
    assert e["primary_parameter"] == "beta_coupon"


def test_primary_test_is_two_sided_and_direction_bounded() -> None:
    p = _yaml()["primary_estimand"]
    assert p["test_sidedness"] == "two_sided"
    assert p["familywise_alpha"] == 0.05
    assert p["expected_direction"] == "positive"
    assert p["success_rule"] == "p_beta_coupon < 0.05 AND beta_coupon > 0"


def test_outcome_has_no_forward_fill() -> None:
    p = _yaml()["primary_outcome"]
    e = _json(ESTIMAND)["outcome"]
    assert p["no_forward_fill"] is True
    assert e["forward_fill"] is False
    assert "s_{t-1}" in p["outcome_definition"]


def test_temporal_firewall() -> None:
    p = _yaml()["temporal_partition"]
    assert p["calibration_power_only"]["end"] == "2018-12-31"
    assert p["confirmatory_retrospective"]["start"] == "2019-01-01"
    assert p["confirmatory_retrospective"]["outcome_locked_until_power_pass"] is True
    assert "choose_primary_parameter" in p["calibration_power_only"]["forbidden_uses"]


def test_power_must_pass_before_confirmatory_outcomes() -> None:
    pg = _yaml()["power_gate_policy"]
    assert pg["must_pass_before_confirmatory_outcome_ingestion"] is True
    assert pg["target_power"] == 0.80
    assert pg["primary_hypotheses"] == 1
    assert pg["multiplicity_correction"] == "none_required_single_primary"
    assert "power < 0.80" in pg["refuse_if"]


def test_geosync_features_are_exploratory_only() -> None:
    g = _yaml()["geosync_features"]
    assert g["status"] == "exploratory_only"
    assert g["forbidden_in_primary_model"] is True
    assert _json(ESTIMAND)["geosync_native_features"] == "exploratory_only"


def test_confirmatory_sources_are_official_and_pti() -> None:
    s = _json(SOURCE_PLAN)
    sources = {x["id"]: x for x in s["confirmatory_sources"]}
    assert {"TREASURY_CASH_PAYDOWN", "NYFED_TGCR", "FED_IORB"} <= set(sources)
    assert all(x["pti_required"] is True for x in sources.values())
    assert s["confirmatory_outcomes_forbidden_before"] == "D002L-P2 TERMINAL_PASS"


def test_literature_overlap_forbids_independent_replication_claim() -> None:
    anchor = _json(SOURCE_PLAN)["literature_anchors"][0]
    assert anchor["date"] == "2026-08-26"
    assert anchor["overlapping_sample"] is True
    assert anchor["independent_replication_claim_allowed"] is False


def test_forbidden_claims_cover_rescue_prediction_alpha_and_causality() -> None:
    claims = set(_yaml()["forbidden_claims"])
    required = {
        "D-002L rescues D-002K",
        "D-002L rescues D-002J",
        "GeoSync predicts systemic crises",
        "GeoSync has trading alpha",
        "this is an independent replication of the 2026 FEDS Note",
        "statistical significance proves causality",
    }
    assert required <= claims


def test_phase_order_is_sequential_and_p1_only_next() -> None:
    p = _yaml()
    assert p["phase_order"] == [
        "D002L-P0",
        "D002L-P1",
        "D002L-P2",
        "D002L-P3",
        "D002L-P4",
        "D002L-P5",
    ]
    assert p["next_legal_node"] == "D002L-P1"
    assert p["canonical_run_authorized"] is False


def test_verdict_capsule_is_p0_pass_only() -> None:
    v = _json(VERDICT)
    assert v["schema_version"] == "D002J-VERDICT-CAPSULE-v1"
    assert v["node_id"] == "D002L-P0"
    assert v["parent_nodes"] == ["D002K-P4"]
    assert v["decision"] == "D002L_PREREG_LOCKED"
    assert v["status"] == "TERMINAL_PASS"
    assert v["allowed_next_nodes"] == ["D002L-P1"]
    assert "D002L-P2" in v["forbidden_next_nodes"]
    assert v["failure_retention"] is None


def test_parent_preregs_remain_byte_exact() -> None:
    assert _sha256(D002J_PREREG) == D002J_PREREG_SHA256
    assert _sha256(D002K_PREREG) == D002K_PREREG_SHA256


def test_stop_conditions_fail_closed() -> None:
    stops = _yaml()["stop_conditions"]
    assert len(stops) >= 5
    assert any("P2 power gate REFUSES" in x for x in stops)
    assert any("INVALIDATE" in x for x in stops)
    assert any("Point-in-time provenance" in x for x in stops)


def test_no_merge_markers_in_p0_package() -> None:
    marker = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)", re.MULTILINE)
    for path in (PREREG, RATIONALE, FAILURE, ESTIMAND, SOURCE_PLAN, VERDICT):
        assert not marker.search(path.read_text(encoding="utf-8")), path
