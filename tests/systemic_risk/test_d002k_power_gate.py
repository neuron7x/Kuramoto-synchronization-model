# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P4 power-first gate guard suite (the truth point of D-002K).

D-002K-P4 computes, honestly, whether the K-P0/P1/P2/P3-locked
3-hypothesis event-conditioned design can reach power >= 0.8 for a
plausible conservative effect at the K-P0-locked Bonferroni alpha. It
scores no data and runs no model: power DESIGN only. Two legitimate
terminals: ``POWER_GATE_PASS`` (P5 becomes legal) or
``POWER_GATE_REFUSED_UNDERPOWERED`` (D-002K halts; fresh D-002L is the
only forward motion). This suite implements BOTH branches honestly --
tests 17/18 are conditional on the actual decision; they do not assume
PASS.

The anti-laundering guard (test 15) asserts the design JSON explicitly
records that the Bonferroni denominator 3 derives from the K-P0-locked
pre-registered hypothesis count, NOT from loosening D-002J-P7's
alpha=4.9e-4 at a fixed hypothesis count. Narrowing scope is not
relaxing statistics -- that distinction is the ethical spine of D-002K.

All multi-line asserts use the msg-var idiom (``_msg = ...`` extracted
above the ``assert``) so the module renders byte-identically under both
black 26.3.1 and ruff-format 0.14.0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.systemic_risk.design_d002k_power_gate import (
    DECISION_PASS,
    DECISION_REFUSED,
    bonferroni_alpha,
    build_power_design,
    build_power_summary,
    effect_size_prior,
    n_min_for_power,
    power_gate_decision,
)

# ---------------------------------------------------------------------------
# Anchors / constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DESIGN_PATH: Path = REPO_ROOT / "artifacts/d002k/power/power_design_v1.json"
SUMMARY_PATH: Path = REPO_ROOT / "artifacts/d002k/power/power_summary_v1.json"
VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002k_p4_verdict_v1.json"
D002J_P7_VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002j_p7_verdict_v1.json"
D002J_P7_POWER_SUMMARY_PATH: Path = REPO_ROOT / "artifacts/d002j/power/power_summary_v1.json"
KP0_PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"

#: K-P0-locked Bonferroni denominator: 3 windows x 1 primary metric.
K_P0_BONFERRONI_DENOMINATOR: int = 3

#: D-002J-P7's correctly-refused denominator (must NOT be undone).
D002J_P7_DENOMINATOR: int = 102

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    assert isinstance(payload, dict), f"{path}: top-level JSON must be object"
    return payload


# ---------------------------------------------------------------------------
# 1-2. Artifact existence
# ---------------------------------------------------------------------------


def test_power_design_exists() -> None:
    assert DESIGN_PATH.is_file(), f"missing power design: {DESIGN_PATH}"


def test_power_summary_exists() -> None:
    assert SUMMARY_PATH.is_file(), f"missing power summary: {SUMMARY_PATH}"


# ---------------------------------------------------------------------------
# 3. Schema versions
# ---------------------------------------------------------------------------


def test_schema_versions() -> None:
    design = _load(DESIGN_PATH)
    summary = _load(SUMMARY_PATH)
    _msg_d = f"design schema must be D002K-POWER-DESIGN-v1; got {design.get('schema_version')!r}"
    assert design["schema_version"] == "D002K-POWER-DESIGN-v1", _msg_d
    _msg_s = f"summary schema must be D002K-POWER-SUMMARY-v1; got {summary.get('schema_version')!r}"
    assert summary["schema_version"] == "D002K-POWER-SUMMARY-v1", _msg_s


# ---------------------------------------------------------------------------
# 4. Parent shas pinned (K-P0 / K-P1 / K-P2 / K-P3) -> prior coupling
# ---------------------------------------------------------------------------


def test_parent_shas_pinned_kp0_kp1_kp2_kp3() -> None:
    design = _load(DESIGN_PATH)
    for key in (
        "parent_kp0_prereg_sha256",
        "parent_kp0_primary_metric_contract_sha256",
        "parent_kp1_observable_contract_sha256",
        "parent_kp2_placebo_registry_sha256",
        "parent_kp3_metric_contract_sha256",
    ):
        val = design.get(key)
        _msg = f"{key} must be a 64-hex sha256; got {val!r}"
        assert isinstance(val, str) and len(val) == 64, _msg
        assert all(c in "0123456789abcdef" for c in val), _msg


# ---------------------------------------------------------------------------
# 5. Alpha policy Bonferroni denominator == n_windows x n_primary == K-P0
# ---------------------------------------------------------------------------


def test_alpha_policy_bonferroni_denominator_is_n_windows_times_n_primary() -> None:
    design = _load(DESIGN_PATH)
    ap = design["alpha_policy"]
    _msg_f = f"alpha family must be bonferroni; got {ap.get('family')!r}"
    assert ap["family"] == "bonferroni", _msg_f
    n_w = ap["n_windows"]
    n_m = ap["n_primary_metrics"]
    denom = ap["denominator"]
    _msg = (
        f"Bonferroni denominator must equal n_windows*n_primary_metrics "
        f"= {n_w}*{n_m} = {n_w * n_m} and the K-P0 lock "
        f"{K_P0_BONFERRONI_DENOMINATOR}; got {denom}"
    )
    assert denom == n_w * n_m == K_P0_BONFERRONI_DENOMINATOR, _msg


# ---------------------------------------------------------------------------
# 6. alpha_per == 0.05 / denominator
# ---------------------------------------------------------------------------


def test_alpha_per_equals_0_05_over_denominator() -> None:
    design = _load(DESIGN_PATH)
    ap = design["alpha_policy"]
    expected = 0.05 / ap["denominator"]
    _msg = f"alpha_per must be 0.05/{ap['denominator']} = {expected!r}; got {ap['alpha_per']!r}"
    assert abs(ap["alpha_per"] - expected) < 1e-12, _msg
    _msg_fn = "bonferroni_alpha(3,1) must equal 0.05/3"
    assert abs(bonferroni_alpha(3, 1) - 0.05 / 3) < 1e-12, _msg_fn


# ---------------------------------------------------------------------------
# 7. Effect-size prior has provenance
# ---------------------------------------------------------------------------


def test_effect_size_prior_has_provenance() -> None:
    design = _load(DESIGN_PATH)
    esa = design["effect_size_assumption"]
    prov = esa.get("provenance", "")
    _msg = f"effect-size provenance must be a non-trivial string; got {prov!r}"
    assert isinstance(prov, str) and len(prov) > 40, _msg
    assert "literature" in prov.lower(), "provenance must cite the literature"


# ---------------------------------------------------------------------------
# 8. Effect-size prior not_inflated flag true
# ---------------------------------------------------------------------------


def test_effect_size_prior_not_inflated_flag_true() -> None:
    design = _load(DESIGN_PATH)
    esa = design["effect_size_assumption"]
    _msg = f"effect_size_assumption.not_inflated must be True; got {esa.get('not_inflated')!r}"
    assert esa["not_inflated"] is True, _msg
    assert effect_size_prior()["not_inflated"] is True, "prior fn flag must be True"


# ---------------------------------------------------------------------------
# 9. Effect-size uses conservative bound
# ---------------------------------------------------------------------------


def test_effect_size_uses_conservative_bound() -> None:
    design = _load(DESIGN_PATH)
    esa = design["effect_size_assumption"]
    cb = esa.get("conservative_bound", "")
    _msg = f"effect-size conservative_bound must be documented; got {cb!r}"
    assert isinstance(cb, str) and len(cb) > 40, _msg
    d = esa["cohen_d"]
    # Conservative: must not exceed the literature 'large' floor (0.80).
    # A larger value would be inflation toward a manufactured PASS.
    _msg_d = f"conservative effect prior must be <= 0.80 (large floor); got d={d!r}"
    assert 0.0 < d <= 0.80, _msg_d


# ---------------------------------------------------------------------------
# 10. n_min computed and positive
# ---------------------------------------------------------------------------


def test_n_min_computed_and_positive() -> None:
    design = _load(DESIGN_PATH)
    n_min = design["n_min"]
    _msg = f"n_min must be a positive int; got {n_min!r}"
    assert isinstance(n_min, int) and n_min > 0, _msg
    fn_n_min = n_min_for_power(0.80, 0.05 / 3, 0.8, 5)
    _msg_fn = f"n_min fn must match design n_min; fn={fn_n_min} design={n_min}"
    assert fn_n_min == n_min, _msg_fn


# ---------------------------------------------------------------------------
# 11. Power target is 0.8
# ---------------------------------------------------------------------------


def test_power_target_is_0_8() -> None:
    design = _load(DESIGN_PATH)
    _msg = f"power_target must be 0.8 (K-P0 lock); got {design.get('power_target')!r}"
    assert design["power_target"] == 0.8, _msg


# ---------------------------------------------------------------------------
# 12. Decision matches canonical_run_authorized flag
# ---------------------------------------------------------------------------


def test_decision_matches_canonical_run_authorized_flag() -> None:
    design = _load(DESIGN_PATH)
    decision = design["decision"]
    authorized = design["canonical_run_authorized"]
    if decision == DECISION_PASS:
        _msg = "PASS must imply canonical_run_authorized=True"
        assert authorized is True, _msg
    elif decision == DECISION_REFUSED:
        _msg = "REFUSED must imply canonical_run_authorized=False"
        assert authorized is False, _msg
    else:
        _msg = f"unexpected decision {decision!r}; canon must be False"
        assert authorized is False, _msg


# ---------------------------------------------------------------------------
# 13. Feasible-n cap present with justification
# ---------------------------------------------------------------------------


def test_feasible_n_cap_present_with_justification() -> None:
    design = _load(DESIGN_PATH)
    cap = design["feasible_n_cap"]
    just = cap.get("justification", "")
    _msg = f"feasible_n_cap.justification must be non-trivial; got {just!r}"
    assert isinstance(just, str) and len(just) > 40, _msg
    anchor = cap.get("d002j_p7_anchor_reference", "")
    _msg_a = f"feasible_n_cap must reference the D-002J-P7 anchor; got {anchor!r}"
    assert isinstance(anchor, str) and "D-002J-P7" in anchor, _msg_a


# ---------------------------------------------------------------------------
# 14. Comparison to D-002J-P7 present
# ---------------------------------------------------------------------------


def test_comparison_to_d002j_p7_present() -> None:
    design = _load(DESIGN_PATH)
    cmp = design["comparison_to_d002j_p7"]
    _msg_dj = (
        f"d002j_bonferroni must be {D002J_P7_DENOMINATOR}; got {cmp.get('d002j_bonferroni')!r}"
    )
    assert cmp["d002j_bonferroni"] == D002J_P7_DENOMINATOR, _msg_dj
    _msg_dk = (
        f"d002k_bonferroni must be {K_P0_BONFERRONI_DENOMINATOR}; "
        f"got {cmp.get('d002k_bonferroni')!r}"
    )
    assert cmp["d002k_bonferroni"] == K_P0_BONFERRONI_DENOMINATOR, _msg_dk
    _msg_ax = f"d002j_refused_axis must be effect_too_small; got {cmp.get('d002j_refused_axis')!r}"
    assert cmp["d002j_refused_axis"] == "effect_too_small", _msg_ax


# ---------------------------------------------------------------------------
# 15. Anti-laundering: narrowing is scope, not alpha relaxation
# ---------------------------------------------------------------------------


def test_narrowing_is_scope_not_alpha_relaxation_asserted() -> None:
    design = _load(DESIGN_PATH)
    cmp = design["comparison_to_d002j_p7"]
    _msg_flag = (
        "comparison_to_d002j_p7.narrowing_is_scope_not_alpha_relaxation "
        "must be True (anti-laundering invariant)"
    )
    assert cmp["narrowing_is_scope_not_alpha_relaxation"] is True, _msg_flag
    derives = design["alpha_policy"].get("denominator_derives_from", "")
    _msg_dv = (
        f"alpha_policy.denominator_derives_from must explicitly record that "
        f"denominator 3 comes from the K-P0-locked hypothesis count and is "
        f"NOT undoing D-002J-P7's alpha; got {derives!r}"
    )
    low = derives.lower()
    assert isinstance(derives, str) and len(derives) > 40, _msg_dv
    assert "k-p0" in low and "hypothes" in low, _msg_dv
    assert "not a relaxation" in low or "not alpha relaxation" in low, _msg_dv


# ---------------------------------------------------------------------------
# 16. D-002J-P7 still REFUSED, byte-exact, retained
# ---------------------------------------------------------------------------


def test_d002j_p7_still_refused_unchanged() -> None:
    p7 = _load(D002J_P7_VERDICT_PATH)
    _msg_d = f"D-002J-P7 must stay POWER_GATE_REFUSED_UNDERPOWERED; got {p7.get('decision')!r}"
    assert p7["decision"] == "POWER_GATE_REFUSED_UNDERPOWERED", _msg_d
    _msg_s = f"D-002J-P7 must stay TERMINAL_REFUSED; got {p7.get('status')!r}"
    assert p7["status"] == "TERMINAL_REFUSED", _msg_s
    p7_pow = _load(D002J_P7_POWER_SUMMARY_PATH)
    _msg_b = (
        f"D-002J-P7 power summary must keep bonferroni_denominator 102; "
        f"got {p7_pow.get('bonferroni_denominator')!r}"
    )
    assert p7_pow["bonferroni_denominator"] == D002J_P7_DENOMINATOR, _msg_b
    dag = _load(REPO_ROOT / "artifacts/governance/verdicts/d002j_verdict_dag_v1.json")
    _msg_r = (
        f"D002J-P7 must stay in rejected_nodes_retained; got {dag.get('rejected_nodes_retained')!r}"
    )
    assert "D002J-P7" in dag["rejected_nodes_retained"], _msg_r


# ---------------------------------------------------------------------------
# 17. CONDITIONAL: if REFUSED -> axis recorded, next is fresh lineage
# ---------------------------------------------------------------------------


def test_if_refused_axis_recorded_and_next_is_fresh_lineage() -> None:
    design = _load(DESIGN_PATH)
    if design["decision"] != DECISION_REFUSED:
        # PASS branch handled by test 18; nothing to assert here.
        return
    axis = design.get("refused_axis")
    _msg_ax = f"REFUSED must record a non-null refused_axis; got {axis!r}"
    assert isinstance(axis, str) and len(axis) > 0, _msg_ax
    verdict = _load(VERDICT_PATH)
    _msg_st = f"REFUSED verdict status must be TERMINAL_REFUSED; got {verdict.get('status')!r}"
    assert verdict["status"] == "TERMINAL_REFUSED", _msg_st
    _msg_nl = (
        f"REFUSED must have empty allowed_next_nodes; got {verdict.get('allowed_next_nodes')!r}"
    )
    assert verdict["allowed_next_nodes"] == [], _msg_nl
    _msg_fb = f"REFUSED must forbid D002K-P5; got {verdict.get('forbidden_next_nodes')!r}"
    assert "D002K-P5" in verdict["forbidden_next_nodes"], _msg_fb
    fr = verdict.get("failure_retention") or ""
    _msg_fr = "failure_retention must point forward to a fresh D-002L pre-registration"
    assert "D-002L" in fr, _msg_fr
    assert verdict["merge_sha"] == "0" * 40, "merge_sha must be 40 zeros"


# ---------------------------------------------------------------------------
# 18. CONDITIONAL: if PASS -> honest power >= 0.8 at feasible n
# ---------------------------------------------------------------------------


def test_if_pass_power_ge_0_8_at_feasible_n() -> None:
    design = _load(DESIGN_PATH)
    if design["decision"] != DECISION_PASS:
        # REFUSED branch handled by test 17; nothing to assert here.
        return
    p = design["power_at_feasible_n"]
    _msg = f"PASS requires honest power>=0.8 at feasible n; got {p!r}"
    assert p >= 0.8, _msg
    verdict = _load(VERDICT_PATH)
    _msg_st = f"PASS verdict status must be TERMINAL_PASS; got {verdict.get('status')!r}"
    assert verdict["status"] == "TERMINAL_PASS", _msg_st
    _msg_nl = f"PASS must allow D002K-P5; got {verdict.get('allowed_next_nodes')!r}"
    assert verdict["allowed_next_nodes"] == ["D002K-P5"], _msg_nl


# ---------------------------------------------------------------------------
# 19. Power-gate decision deterministic (run twice -> identical)
# ---------------------------------------------------------------------------


def test_power_gate_decision_deterministic() -> None:
    a = build_power_design("2026-05-15T00:00:00Z")
    b = build_power_design("2026-05-15T00:00:00Z")
    _msg = "build_power_design must be byte-deterministic for a fixed timestamp"
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), _msg
    g1 = power_gate_decision(0.80, 0.05 / 3)
    g2 = power_gate_decision(0.80, 0.05 / 3)
    _msg_g = "power_gate_decision must be deterministic"
    assert g1 == g2, _msg_g
    s1 = build_power_summary("2026-05-15T00:00:00Z")
    s2 = build_power_summary("2026-05-15T00:00:00Z")
    _msg_s = "summary must be deterministic"
    _s1 = json.dumps(s1, sort_keys=True)
    _s2 = json.dumps(s2, sort_keys=True)
    assert _s1 == _s2, _msg_s


# ---------------------------------------------------------------------------
# 20. No data scoring performed
# ---------------------------------------------------------------------------


def test_no_data_scoring_performed() -> None:
    design = _load(DESIGN_PATH)
    summary = _load(SUMMARY_PATH)
    _msg_d = "design must assert no_data_scoring_performed=True"
    assert design.get("no_data_scoring_performed") is True, _msg_d
    _msg_m = "design must assert no_model_run_performed=True"
    assert design.get("no_model_run_performed") is True, _msg_m
    _msg_r = "design must assert no_real_data=True"
    assert design.get("no_real_data") is True, _msg_r
    _msg_s = "summary must assert no_canonical_run_executed=True"
    assert summary.get("no_canonical_run_executed") is True, _msg_s


# ---------------------------------------------------------------------------
# 21. No systemic-risk prediction claim
# ---------------------------------------------------------------------------


def test_no_systemic_risk_prediction_claim() -> None:
    design = _load(DESIGN_PATH)
    blob = json.dumps(design).lower()
    forbidden = (
        "predicts systemic cris",
        "bank-level validated",
        "proves interbank contagion",
        "forecasts the next crisis",
    )
    for phrase in forbidden:
        _msg = f"design must not state/imply forbidden claim {phrase!r}"
        assert phrase not in blob, _msg
    cb = design.get("claim_boundary", "")
    _msg_cb = f"claim_boundary must scope this to power design only; got {cb!r}"
    assert "Power design only" in cb, _msg_cb


# ---------------------------------------------------------------------------
# 22. No D-002K prereg or prior-phase edit (frozen byte-exact)
# ---------------------------------------------------------------------------


def test_no_d002k_prereg_or_prior_phase_edit() -> None:
    import hashlib

    frozen = {
        "docs/governance/D002K_PREREGISTRATION.yaml": (
            "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"  # pragma: allowlist secret
        ),
        "artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json": (
            "7effc088810ba5933850618312fcad369fdac0386b4a3cab6f14455feeb5a569"  # pragma: allowlist secret
        ),
        "artifacts/d002k/observables/source_observable_contract_v1.json": (
            "952739cbfe4aa16a54eb5684be4bbd653e820eaf92113418e379a3bf8a2a71c3"  # pragma: allowlist secret
        ),
        "artifacts/d002k/placebo/matched_placebo_registry_v1.json": (
            "435d41df868859f25811236fa4675d01f202682c693d06208922c263ace09413"  # pragma: allowlist secret
        ),
        "artifacts/d002k/metrics/event_metric_contract_v1.json": (
            "9c2ce60b6fbcb52e969d71e2137d8345c35f2f71ff9dcc1d64b9ad759d2480ce"  # pragma: allowlist secret
        ),
    }
    for rel, want in frozen.items():
        got = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
        _msg = f"FROZEN drift: {rel} sha256={got} expected {want}"
        assert got == want, _msg


# ---------------------------------------------------------------------------
# 23. No canonical run unless gate PASS
# ---------------------------------------------------------------------------


def test_no_canonical_run_unless_gate_pass() -> None:
    design = _load(DESIGN_PATH)
    dag = _load(REPO_ROOT / "artifacts/governance/verdicts/d002j_verdict_dag_v1.json")
    _msg_dag = "DAG canonical_run_authorized_anywhere must be False"
    assert dag["canonical_run_authorized_anywhere"] is False, _msg_dag
    if design["decision"] != DECISION_PASS:
        _msg = "non-PASS design must keep canonical_run_authorized=False"
        assert design["canonical_run_authorized"] is False, _msg


# ---------------------------------------------------------------------------
# 24. No unresolved merge markers
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        REPO_ROOT / "tools/systemic_risk/design_d002k_power_gate.py",
        REPO_ROOT / "tests/systemic_risk/test_d002k_power_gate.py",
        DESIGN_PATH,
        SUMMARY_PATH,
        VERDICT_PATH,
        REPO_ROOT / "docs/research/D002K_POWER_FIRST_REPORT.md",
    ]
    for path in targets:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            _msg = f"unresolved merge marker in {path} line {i}: {line!r}"
            assert not _MARKER.match(line), _msg
