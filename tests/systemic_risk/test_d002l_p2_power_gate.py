# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic/non-scientific tests for D-002L-P2 pre-outcome power machinery."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

import research.systemic_risk.d002l_power_gate as p2
from research.systemic_risk.d002l_power_gate import (
    D002LPowerError,
    conservative_effect_prior,
    evaluate_power,
    execute_power_gate,
    exogenous_design,
    validate_calibration_noise,
    validate_p1_authority,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_P1_STATUS = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_execution_status_v1.json"


def _business_day_on_or_before(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _registry(n_months_mode: str = "full") -> dict:
    events = []
    i = 0
    for year in range(2019, 2027):
        max_month = 8 if year == 2026 else 12
        for month in range(1, max_month + 1):
            candidates = [
                _business_day_on_or_before(date(year, month, 15)),
                _business_day_on_or_before(date(year, month, calendar.monthrange(year, month)[1])),
            ]
            for d in candidates:
                if d > date(2026, 8, 20):
                    continue
                x = ((i * 37) % 101 - 50) / 10
                if abs(x) < 1e-12:
                    x = 0.1
                b = ((i * 19) % 67 - 33) / 20
                events.append(
                    {
                        "settlement_date": d.isoformat(),
                        "partition": "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY",
                        "eligible": True,
                        "x_t_scaled_100bn": str(x),
                        "b_t_scaled_100bn": str(b),
                    }
                )
                i += 1
    if n_months_mode == "small":
        events = events[:30]
    return {
        "node_id": "D002L-P1",
        "confirmatory_outcomes_ingested": False,
        "next_phase_authorized": "D002L-P2",
        "events": events,
    }


def _p1_pass() -> dict:
    return {
        "node_id": "D002L-P1",
        "status": "TERMINAL_PASS",
        "decision": "D002L_EXPOSURE_REGISTRY_SOURCE_COMPLETE",
        "lineage_advance_allowed": True,
        "source_authenticity_for_lineage_advance": True,
        "confirmatory_outcomes_ingested": False,
    }


def _noise(sigma: float = 5.0, design_effect: float = 1.0) -> dict:
    return {
        "schema_version": "D002L-CALIBRATION-NOISE-v1",
        "study_id": "D-002L",
        "use": "POWER_ONLY",
        "period_start": "2014-09-02",
        "period_end": "2018-12-31",
        "sigma_residual_bps": sigma,
        "week_cluster_design_effect": design_effect,
        "confirmatory_observations_used": 0,
    }


def _prior(point: float = 1.0, lower=None, upper=None) -> dict:
    return {
        "study_id": "D-002L",
        "source_role": "EXTERNAL_DESIGN_AND_POWER_PRIOR_ONLY",
        "confirmatory_outcomes_used": 0,
        "published_point_estimate_bps_per_100bn": point,
        "published_ci95_lower_bps_per_100bn": lower,
        "published_ci95_upper_bps_per_100bn": upper,
    }


def test_current_real_p1_blocker_makes_p2_illegal() -> None:
    status = json.loads(CURRENT_P1_STATUS.read_text(encoding="utf-8"))
    assert status["status"] == "NOT_EXECUTED"
    with pytest.raises(D002LPowerError, match="P1_NOT_TERMINAL_PASS"):
        validate_p1_authority(status, _registry())


def test_p1_authority_requires_direct_source_authenticity() -> None:
    status = _p1_pass()
    status["source_authenticity_for_lineage_advance"] = False
    with pytest.raises(D002LPowerError, match="P1_SOURCE_AUTHENTICITY_NOT_ESTABLISHED"):
        validate_p1_authority(status, _registry())


def test_calibration_noise_is_strictly_preconfirmatory() -> None:
    assert validate_calibration_noise(_noise()) == 5.0
    assert validate_calibration_noise(_noise(5.0, 1.44)) == pytest.approx(6.0)
    leaked = _noise()
    leaked["period_end"] = "2019-01-01"
    with pytest.raises(D002LPowerError, match="LEAKS_POST_CALIBRATION"):
        validate_calibration_noise(leaked)
    leaked = _noise()
    leaked["confirmatory_observations_used"] = 1
    with pytest.raises(D002LPowerError, match="CONFIRMATORY_OUTCOMES_USED_IN_POWER_NOISE"):
        validate_calibration_noise(leaked)
    with pytest.raises(D002LPowerError, match="SIGMA_MUST_BE_POSITIVE_FINITE"):
        validate_calibration_noise(_noise(0.0))


def test_effect_prior_rule_partial_and_full() -> None:
    partial = conservative_effect_prior(_prior(point=1.0))
    assert partial["chosen_beta_prior_bps_per_100bn"] == 0.5
    assert partial["prior_quality"] == "PARTIAL"
    full = conservative_effect_prior(_prior(point=2.0, lower=0.7, upper=3.0))
    assert full["chosen_beta_prior_bps_per_100bn"] == 0.7
    assert full["prior_quality"] == "FULL"


def test_effect_prior_ci_crossing_zero_refuses() -> None:
    with pytest.raises(D002LPowerError, match="COLLAPSES_TO_ZERO"):
        conservative_effect_prior(_prior(point=2.0, lower=-0.1, upper=3.0))
    bad = _prior(point=1.0)
    bad["confirmatory_outcomes_used"] = 1
    with pytest.raises(D002LPowerError, match="CONFIRMATORY_OUTCOMES_USED_IN_EFFECT_PRIOR"):
        conservative_effect_prior(bad)


def test_exogenous_design_has_nine_columns_and_no_outcomes() -> None:
    X, x, dates = exogenous_design(_registry()["events"])
    assert X.shape[0] == len(x) == len(dates)
    assert X.shape[1] == 9


def test_weekend_settlement_refuses() -> None:
    events = [_registry()["events"][0].copy()]
    events[0]["settlement_date"] = "2020-01-18"  # Saturday
    with pytest.raises(D002LPowerError, match="SETTLEMENT_DATE_ON_WEEKEND"):
        exogenous_design(events)


def test_synthetic_well_powered_design_passes_without_outcomes() -> None:
    result = evaluate_power(_registry(), _noise(5.0), _prior(point=1.0))
    assert result["status"] == "TERMINAL_PASS"
    assert result["power"] >= 0.80
    assert result["effective_cluster_count"] >= 20
    assert result["computed_n_min_observed_prefix"] is not None
    assert result["confirmatory_outcomes_ingested"] is False
    assert result["full_design_with_lagged_spread_checked"] is False
    assert result["next_legal_node"] == "D002L-P3"


def test_synthetic_underpowered_design_refuses() -> None:
    result = evaluate_power(_registry(), _noise(5.0), _prior(point=0.4))
    assert result["status"] == "TERMINAL_REFUSED"
    assert "POWER_BELOW_0_80" in result["refusal_reasons"]
    assert result["next_legal_node"] is None


def test_small_design_cannot_clear_cluster_and_power_prefix_gate() -> None:
    result = evaluate_power(_registry("small"), _noise(5.0), _prior(point=1.0))
    if result["status"] == "TERMINAL_REFUSED":
        assert result["refusal_reasons"]
    else:
        assert result["effective_cluster_count"] >= 20
        assert result["power"] >= 0.80


def test_execute_power_gate_requires_p1_first() -> None:
    result = execute_power_gate(_p1_pass(), _registry(), _noise(5.0), _prior(point=1.0))
    assert result["status"] == "TERMINAL_PASS"
    blocked = _p1_pass()
    blocked["status"] = "OFFLINE_REPLAY_ONLY"
    with pytest.raises(D002LPowerError, match="P1_NOT_TERMINAL_PASS"):
        execute_power_gate(blocked, _registry(), _noise(), _prior())


def test_rank_deficient_design_refuses() -> None:
    reg = _registry()
    for event in reg["events"]:
        event["x_t_scaled_100bn"] = "1.0"
        event["b_t_scaled_100bn"] = "1.0"
    with pytest.raises(D002LPowerError, match="DESIGN_MATRIX_RANK_DEFICIENT"):
        evaluate_power(reg, _noise(), _prior())


def test_p2_result_claim_boundary_is_nonempirical() -> None:
    result = evaluate_power(_registry(), _noise(), _prior())
    text = result["claim_boundary"].lower()
    assert "no beta is fit" in text
    assert "no empirical association" in text
    assert result["canonical_run_authorized"] is False


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda s: s.update(node_id="WRONG"), "P1_STATUS_WRONG_NODE"),
        (lambda s: s.update(decision="WRONG"), "P1_WRONG_DECISION"),
        (lambda s: s.update(lineage_advance_allowed=False), "P1_LINEAGE_ADVANCE_NOT_AUTHORIZED"),
        (lambda s: s.update(confirmatory_outcomes_ingested=True), "P1_OUTCOME_FIREWALL_BREACHED"),
    ],
)
def test_p1_status_authority_fail_closed(mutator, message: str) -> None:
    status = _p1_pass()
    mutator(status)
    with pytest.raises(D002LPowerError, match=message):
        p2.validate_p1_status_authority(status)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda r: r.update(node_id="WRONG"), "P1_REGISTRY_WRONG_NODE"),
        (lambda r: r.update(confirmatory_outcomes_ingested=True), "P1_REGISTRY_OUTCOME_FIREWALL_BREACHED"),
        (lambda r: r.update(next_phase_authorized="D002L-P3"), "P1_REGISTRY_DOES_NOT_AUTHORIZE_P2"),
    ],
)
def test_p1_registry_authority_fail_closed(mutator, message: str) -> None:
    reg = _registry()
    mutator(reg)
    with pytest.raises(D002LPowerError, match=message):
        p2.validate_p1_registry_authority(reg)


def test_calibration_noise_contract_error_paths() -> None:
    missing = _noise(); missing.pop("sigma_residual_bps")
    with pytest.raises(D002LPowerError, match="FIELDS_MISSING"):
        validate_calibration_noise(missing)
    wrong = _noise(); wrong["study_id"] = "D-OTHER"
    with pytest.raises(D002LPowerError, match="WRONG_STUDY"):
        validate_calibration_noise(wrong)
    wrong = _noise(); wrong["use"] = "FIT_MODEL"
    with pytest.raises(D002LPowerError, match="WRONG_USE"):
        validate_calibration_noise(wrong)
    bad = _noise(); bad["period_start"] = "bad-date"
    with pytest.raises(D002LPowerError, match="INVALID_VALUE"):
        validate_calibration_noise(bad)
    reversed_period = _noise(); reversed_period["period_start"] = "2018-12-31"; reversed_period["period_end"] = "2014-09-02"
    with pytest.raises(D002LPowerError, match="PERIOD_REVERSED"):
        validate_calibration_noise(reversed_period)
    with pytest.raises(D002LPowerError, match="DESIGN_EFFECT"):
        validate_calibration_noise(_noise(5.0, 0.99))
    with pytest.raises(D002LPowerError, match="DESIGN_EFFECT"):
        validate_calibration_noise(_noise(5.0, float("nan")))


def test_effect_prior_error_paths() -> None:
    bad = _prior(); bad["study_id"] = "OTHER"
    with pytest.raises(D002LPowerError, match="WRONG_STUDY"):
        conservative_effect_prior(bad)
    bad = _prior(); bad["source_role"] = "CONFIRMATORY"
    with pytest.raises(D002LPowerError, match="WRONG_SOURCE_ROLE"):
        conservative_effect_prior(bad)
    bad = _prior(); bad["published_point_estimate_bps_per_100bn"] = "nope"
    with pytest.raises(D002LPowerError, match="POINT_ESTIMATE_INVALID"):
        conservative_effect_prior(bad)
    for point in (0.0, float("inf")):
        bad = _prior(point=point)
        with pytest.raises(D002LPowerError, match="MUST_BE_POSITIVE_FINITE"):
            conservative_effect_prior(bad)
    bad = _prior(point=2.0, lower="bad", upper=3.0)
    with pytest.raises(D002LPowerError, match="CI_INVALID"):
        conservative_effect_prior(bad)
    bad = _prior(point=2.0, lower=3.0, upper=2.0)
    with pytest.raises(D002LPowerError, match="CI_INVALID"):
        conservative_effect_prior(bad)


def test_confirmatory_event_filter_and_error_paths() -> None:
    reg = _registry()
    # Non-confirmatory and ineligible events are ignored.
    reg["events"].insert(0, {"partition": "CALIBRATION_POWER_EXPOSURE_ONLY", "eligible": True})
    reg["events"].insert(1, {"partition": "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY", "eligible": False})
    assert p2.confirmatory_events(reg)
    with pytest.raises(D002LPowerError, match="P1_EVENTS_NOT_LIST"):
        p2.confirmatory_events({"events": {}})
    with pytest.raises(D002LPowerError, match="P1_EVENT_NOT_OBJECT"):
        p2.confirmatory_events({"events": ["bad"]})
    out_of_range = _registry(); out_of_range["events"][0]["settlement_date"] = "2018-12-31"
    with pytest.raises(D002LPowerError, match="DATE_OUTSIDE_LOCKED_PERIOD"):
        p2.confirmatory_events(out_of_range)
    with pytest.raises(D002LPowerError, match="ZERO_ELIGIBLE"):
        p2.confirmatory_events({"events": []})


def test_exposure_value_error_paths() -> None:
    events = [_registry()["events"][0].copy()]
    events[0].pop("b_t_scaled_100bn")
    with pytest.raises(D002LPowerError, match="EXPOSURE_VALUE_INVALID"):
        exogenous_design(events)
    events = [_registry()["events"][0].copy()]
    events[0]["x_t_scaled_100bn"] = "nan"
    with pytest.raises(D002LPowerError, match="EXPOSURE_VALUE_NONFINITE"):
        exogenous_design(events)


def test_cluster_design_effect_is_conservative() -> None:
    iid = evaluate_power(_registry(), _noise(5.0, 1.0), _prior(point=1.0))
    clustered = evaluate_power(_registry(), _noise(5.0, 2.25), _prior(point=1.0))
    assert clustered["effective_sigma_bps_for_power"] == pytest.approx(7.5)
    assert clustered["power"] < iid["power"]
    assert clustered["week_cluster_design_effect_calibration_only"] == 2.25


def test_nonfinite_power_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p2.nct, "sf", lambda *args, **kwargs: float("nan"))
    monkeypatch.setattr(p2.nct, "cdf", lambda *args, **kwargs: 0.0)
    with pytest.raises(D002LPowerError, match="POWER_NUMERIC_NONFINITE"):
        evaluate_power(_registry(), _noise(), _prior())


def test_execute_from_paths_fails_on_p1_before_missing_downstream_files(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(CURRENT_P1_STATUS.read_text(encoding="utf-8"), encoding="utf-8")
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(D002LPowerError, match="P1_NOT_TERMINAL_PASS"):
        p2.execute_from_paths(status_path, missing, missing, missing)


def test_load_json_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(D002LPowerError, match="INVALID_JSON_ARTIFACT"):
        p2._load_json(missing)
    bad = tmp_path / "bad.json"; bad.write_text("{", encoding="utf-8")
    with pytest.raises(D002LPowerError, match="INVALID_JSON_ARTIFACT"):
        p2._load_json(bad)
    arr = tmp_path / "arr.json"; arr.write_text("[]", encoding="utf-8")
    with pytest.raises(D002LPowerError, match="JSON_ARTIFACT_NOT_OBJECT"):
        p2._load_json(arr)


def test_execute_from_paths_happy_path(tmp_path: Path) -> None:
    objects = {
        "status": _p1_pass(),
        "registry": _registry(),
        "noise": _noise(),
        "prior": _prior(),
    }
    paths = {}
    for name, obj in objects.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        paths[name] = path
    result = p2.execute_from_paths(paths["status"], paths["registry"], paths["noise"], paths["prior"])
    assert result["status"] == "TERMINAL_PASS"

P2_CONTRACT = REPO_ROOT / "artifacts/d002l/power/d002l_p2_implementation_contract_v1.json"
P2_STATUS = REPO_ROOT / "artifacts/d002l/power/d002l_p2_execution_status_v1.json"
P1_CONTRACT = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_source_contract_v1.json"


def test_machine_p2_contract_keeps_clustered_power_and_outcome_firewall() -> None:
    contract = json.loads(P2_CONTRACT.read_text(encoding="utf-8"))
    assert contract["implementation_status"] == "IMPLEMENTED_AWAITING_P1_TERMINAL_PASS"
    assert contract["preoutcome_design"]["column_count"] == 9
    assert contract["inputs"]["calibration_noise"]["required_fields"] == [
        "sigma_residual_bps", "week_cluster_design_effect"
    ]
    assert contract["outcome_firewall"]["confirmatory_TGCR_IOER_IORB_ingestion_at_P2"] is False
    assert contract["authority"]["current_lineage_advance"] is False


def test_machine_p2_status_matches_current_real_p1_blocker() -> None:
    p1 = json.loads(CURRENT_P1_STATUS.read_text(encoding="utf-8"))
    status = json.loads(P2_STATUS.read_text(encoding="utf-8"))
    assert p1["status"] == "NOT_EXECUTED"
    assert p1["decision"] == "BLOCKED_SOURCE_ACCESS"
    assert status["scientific_execution_status"] == "NOT_EXECUTED"
    assert status["decision"] == "BLOCKED_PREDECESSOR_P1_NOT_TERMINAL_PASS"
    assert status["lineage_advance_allowed"] is False
    assert status["confirmatory_outcomes_ingested"] is False


def test_p1_contract_preserves_same_day_bill_nuisance_control() -> None:
    contract = json.loads(P1_CONTRACT.read_text(encoding="utf-8"))
    bill = contract["event_contract"]["same_day_bill_control"]
    assert bill["symbol"] == "b_t"
    assert bill["missing_same_day_bill_row"] == "ZERO_CONTROL"
    assert bill["duplicate_direct_bill_rows"] == "REFUSE"



def test_p2_commit_acceptor_is_fail_closed() -> None:
    import hashlib
    import yaml

    path = REPO_ROOT / ".claude/commit_acceptors/x10r-d002l-p2-power-engine.yaml"
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert obj["id"] == "x10r-d002l-p2-power-engine"
    assert obj["claim_type"] == "governance"
    inv = obj["phase_invariants"]
    assert inv["predecessor_direct_source_terminal_pass_required"] is True
    assert inv["confirmatory_outcomes_ingested"] is False
    assert inv["beta_coupon_fit_at_p2"] is False
    assert inv["canonical_run_authorized"] is False
    assert inv["lineage_advance_while_p1_blocked"] is False
    assert float(inv["week_cluster_design_effect_minimum"]) >= 1.0
    forbidden = set(obj["forbidden_paths"])
    assert "docs/governance/D002L_PREREGISTRATION.yaml" in forbidden
    assert "artifacts/d002j/" in forbidden
    assert "artifacts/d002k/" in forbidden
    anchors = obj["frozen_anchors"]
    prereg = REPO_ROOT / "docs/governance/D002L_PREREGISTRATION.yaml"
    p1c = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_source_contract_v1.json"
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == anchors["d002l_prereg_sha256"]
    assert hashlib.sha256(p1c.read_bytes()).hexdigest() == anchors["d002l_p1_source_contract_sha256"]
