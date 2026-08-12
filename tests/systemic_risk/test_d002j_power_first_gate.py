# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P7 power-first canonical-run gate guard tests.

Every test guards one structural / honesty invariant of the P7 power
design. Tests 3-9 are phase-coupling guards: the P7 cell space must be a
subset of {P5 substrates} x {P6 nulls} x {P2 windows}, and every
effect-size prior must be sourced from a P4 positive control. The gate's
WHOLE PURPOSE is to refuse a blind sweep; a truthful
POWER_GATE_REFUSED_UNDERPOWERED is a scientific win, so the decision
tests assert the PASS<=>authorized<=>REFUSED equivalences rather than a
particular verdict.

All multi-line asserts use the ``msg = ...`` idiom so the file renders
byte-identically under both black and ruff-format.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tools.systemic_risk.design_d002j_power_grid import (
    REPO_ROOT,
    bonferroni_denominator,
    effect_size_prior,
    mde,
    n_min,
    run_power_design,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

POWER_DIR: Path = REPO_ROOT / "artifacts/d002j/power"
REPORT_PATH: Path = POWER_DIR / "power_report_v1.json"
SUMMARY_PATH: Path = POWER_DIR / "power_summary_v1.json"

SUB_MANIFEST_PATH: Path = (
    REPO_ROOT / "artifacts/d002j/substrates/substrate_candidate_manifest_v1.json"
)
NULL_MANIFEST_PATH: Path = REPO_ROOT / "artifacts/d002j/nulls/null_hierarchy_manifest_v1.json"
PC_MANIFEST_PATH: Path = (
    REPO_ROOT / "artifacts/d002j/positive_controls/positive_control_manifest_v1.json"
)
CW_REGISTRY_PATH: Path = REPO_ROOT / "artifacts/d002j/crisis_windows/crisis_window_registry_v1.json"

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    with REPORT_PATH.open(encoding="utf-8") as fh:
        payload: dict[str, Any] = json.load(fh)
    assert isinstance(payload, dict)
    return payload


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    with SUMMARY_PATH.open(encoding="utf-8") as fh:
        payload: dict[str, Any] = json.load(fh)
    assert isinstance(payload, dict)
    return payload


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


# ---------------------------------------------------------------------------
# 1-2: artifacts exist
# ---------------------------------------------------------------------------


def test_power_report_exists(report: dict[str, Any]) -> None:
    msg_file = f"power report must exist at {REPORT_PATH}"
    assert REPORT_PATH.is_file(), msg_file
    msg_schema = (
        f"report schema must be D002J-POWER-REPORT-v1; got {report.get('schema_version')!r}"
    )
    assert report["schema_version"] == "D002J-POWER-REPORT-v1", msg_schema


def test_power_summary_exists(summary: dict[str, Any]) -> None:
    msg_file = f"power summary must exist at {SUMMARY_PATH}"
    assert SUMMARY_PATH.is_file(), msg_file
    msg_schema = (
        f"summary schema must be D002J-POWER-SUMMARY-v1; got {summary.get('schema_version')!r}"
    )
    assert summary["schema_version"] == "D002J-POWER-SUMMARY-v1", msg_schema


# ---------------------------------------------------------------------------
# 3: effect-size priors sourced from P4 controls (phase-coupling P7->P4)
# ---------------------------------------------------------------------------


def test_effect_size_priors_sourced_from_p4_controls(report: dict[str, Any]) -> None:
    pc = _load(PC_MANIFEST_PATH)
    pc_ids = {f["control_family_id"] for f in pc["control_families"]}
    esa = report["effect_size_assumption"]
    assert isinstance(esa, dict) and esa, "effect_size_assumption must be a non-empty object"
    for sid, spec in esa.items():
        src = spec["source_pc_id"]
        msg_src = f"substrate {sid!r} prior source_pc_id {src!r} must be a real P4 control"
        assert src in pc_ids, msg_src
        msg_rat = f"substrate {sid!r} prior must carry a non-empty rationale"
        assert isinstance(spec["rationale"], str) and spec["rationale"].strip(), msg_rat


# ---------------------------------------------------------------------------
# 4: no effect size invented without a PC source
# ---------------------------------------------------------------------------


def test_no_effect_size_invented_without_pc_source(report: dict[str, Any]) -> None:
    pc = _load(PC_MANIFEST_PATH)
    sub = _load(SUB_MANIFEST_PATH)
    pc_by_id = {f["control_family_id"]: f for f in pc["control_families"]}
    esa = report["effect_size_assumption"]
    declared_subs = {s["substrate_id"] for s in sub["substrates"]}
    msg_all = f"every P5 substrate must have a prior; mismatch: {set(esa)} vs {declared_subs}"
    assert set(esa) == declared_subs, msg_all
    for sid, spec in esa.items():
        pcf = pc_by_id[spec["source_pc_id"]]
        # The prior value must be a shrink (never inflate the P4 magnitude).
        msg_shrink = (
            f"{sid!r} attenuated d={spec['value']} must not exceed the P4 "
            f"pass magnitude {pcf['pass_threshold']['value']} (shrink-only)"
        )
        assert spec["value"] <= float(pcf["pass_threshold"]["value"]) + 1e-9, msg_shrink
        msg_pos = f"{sid!r} effect prior must be strictly positive, got {spec['value']}"
        assert spec["value"] > 0.0, msg_pos


# ---------------------------------------------------------------------------
# 5: alpha policy Bonferroni denominator explicit
# ---------------------------------------------------------------------------


def test_alpha_policy_bonferroni_denominator_explicit(report: dict[str, Any]) -> None:
    ap = report["alpha_policy"]
    assert isinstance(ap, dict), "alpha_policy must be an object"
    msg_fam = f"alpha family must be 'bonferroni'; got {ap.get('family')!r}"
    assert ap["family"] == "bonferroni", msg_fam
    denom = ap["denominator"]
    msg_int = f"Bonferroni denominator must be a positive int; got {denom!r}"
    assert isinstance(denom, int) and denom > 0, msg_int
    msg_deriv = "alpha_policy.derivation must be a non-empty explicit string"
    assert isinstance(ap["derivation"], str) and ap["derivation"].strip(), msg_deriv
    expected_alpha = 0.05 / denom
    msg_alpha = f"alpha_per_cell must equal 0.05/{denom}; got {ap['alpha_per_cell']!r}"
    assert abs(ap["alpha_per_cell"] - expected_alpha) < 1e-15, msg_alpha


# ---------------------------------------------------------------------------
# 6: Bonferroni denominator matches the cell count (P7->{P5,P6,P2})
# ---------------------------------------------------------------------------


def test_bonferroni_denominator_matches_cell_count(report: dict[str, Any]) -> None:
    ap = report["alpha_policy"]
    per_cell = report["per_cell"]
    msg_match = (
        f"Bonferroni denominator {ap['denominator']} must equal the number "
        f"of per_cell entries {len(per_cell)}"
    )
    assert ap["denominator"] == len(per_cell), msg_match
    # Independent recomputation from P5/P6/P2 manifests.
    sub = _load(SUB_MANIFEST_PATH)
    null_m = _load(NULL_MANIFEST_PATH)
    appl: dict[str, int] = {}
    for n in null_m["null_families"]:
        for s in n["applicable_substrates"]:
            appl[s] = appl.get(s, 0) + 1
    expected = 0
    for s in sub["substrates"]:
        expected += (
            appl.get(s["substrate_id"], 0) * len(s["crisis_windows"]) * len(s["observable_outputs"])
        )
    msg_recompute = f"recomputed cell count {expected} must equal denominator {ap['denominator']}"
    assert expected == ap["denominator"], msg_recompute


# ---------------------------------------------------------------------------
# 7: per-cell substrate in P5 manifest (phase-coupling P7->P5)
# ---------------------------------------------------------------------------


def test_per_cell_substrate_in_p5_manifest(report: dict[str, Any]) -> None:
    sub = _load(SUB_MANIFEST_PATH)
    p5_subs = {s["substrate_id"] for s in sub["substrates"]}
    seen: set[str] = set()
    for cell in report["per_cell"]:
        msg = f"per_cell substrate {cell['substrate']!r} must be a P5 substrate {sorted(p5_subs)}"
        assert cell["substrate"] in p5_subs, msg
        seen.add(cell["substrate"])
    msg_cover = f"every P5 substrate must appear in some cell; missing {p5_subs - seen}"
    assert seen == p5_subs, msg_cover


# ---------------------------------------------------------------------------
# 8: per-cell null in P6 manifest (phase-coupling P7->P6)
# ---------------------------------------------------------------------------


def test_per_cell_null_in_p6_manifest(report: dict[str, Any]) -> None:
    null_m = _load(NULL_MANIFEST_PATH)
    null_appl: dict[str, set[str]] = {}
    for n in null_m["null_families"]:
        null_appl[n["null_id"]] = set(n["applicable_substrates"])
    for cell in report["per_cell"]:
        nid = cell["null"]
        msg_exists = f"per_cell null {nid!r} must be a declared P6 null family"
        assert nid in null_appl, msg_exists
        msg_appl = (
            f"null {nid!r} paired with substrate {cell['substrate']!r} but "
            f"that substrate is not in the null's applicable_substrates"
        )
        assert cell["substrate"] in null_appl[nid], msg_appl


# ---------------------------------------------------------------------------
# 9: per-cell window in P2 registry (phase-coupling P7->P2)
# ---------------------------------------------------------------------------


def test_per_cell_window_in_p2_registry(report: dict[str, Any]) -> None:
    cw = _load(CW_REGISTRY_PATH)
    registry_windows = {w["window_id"] for w in cw["windows"]}
    sub = _load(SUB_MANIFEST_PATH)
    sub_windows = {s["substrate_id"]: set(s["crisis_windows"]) for s in sub["substrates"]}
    for cell in report["per_cell"]:
        w = cell["window"]
        msg_reg = f"per_cell window {w!r} must be in the P2 crisis-window registry"
        assert w in registry_windows, msg_reg
        msg_decl = (
            f"window {w!r} paired with substrate {cell['substrate']!r} but "
            f"that substrate does not declare it in P5 crisis_windows"
        )
        assert w in sub_windows[cell["substrate"]], msg_decl


# ---------------------------------------------------------------------------
# 10: n_min computed for every cell
# ---------------------------------------------------------------------------


def test_n_min_computed_for_every_cell(report: dict[str, Any]) -> None:
    for cell in report["per_cell"]:
        nm = cell["n_min"]
        msg = f"cell n_min must be a positive int; got {nm!r} for {cell}"
        assert isinstance(nm, int) and nm > 0, msg
    # Spot-check against the formula directly.
    alpha = report["alpha_policy"]["alpha_per_cell"]
    sample = report["per_cell"][0]
    recomputed = n_min(sample["assumed_effect"], alpha, report["power_target"])
    msg_formula = f"recomputed n_min {recomputed} must match cell n_min {sample['n_min']}"
    assert recomputed == sample["n_min"], msg_formula


# ---------------------------------------------------------------------------
# 11: power target is 0.8
# ---------------------------------------------------------------------------


def test_power_target_is_0_8(report: dict[str, Any], summary: dict[str, Any]) -> None:
    msg_r = f"report power_target must be 0.8; got {report.get('power_target')!r}"
    assert report["power_target"] == 0.8, msg_r
    msg_s = f"summary power_target must be 0.8; got {summary.get('power_target')!r}"
    assert summary["power_target"] == 0.8, msg_s


# ---------------------------------------------------------------------------
# 12: minimum detectable effect present
# ---------------------------------------------------------------------------


def test_minimum_detectable_effect_present(report: dict[str, Any]) -> None:
    mde_g = report["minimum_detectable_effect_global"]
    msg = f"minimum_detectable_effect_global must be a positive float; got {mde_g!r}"
    assert isinstance(mde_g, (int, float)) and mde_g > 0.0, msg
    for cell in report["per_cell"]:
        msg_c = f"per-cell mde must be positive; got {cell['mde']!r}"
        assert cell["mde"] > 0.0, msg_c


# ---------------------------------------------------------------------------
# 13: runtime budget present with a measured per-sim cost
# ---------------------------------------------------------------------------


def test_runtime_budget_present_with_per_sim_measured(report: dict[str, Any]) -> None:
    rb = report["runtime_budget"]
    assert isinstance(rb, dict), "runtime_budget must be an object"
    ps = rb["per_sim_seconds_measured"]
    msg_ps = f"per_sim_seconds_measured must be a positive float; got {ps!r}"
    assert isinstance(ps, (int, float)) and ps > 0.0, msg_ps
    msg_local = f"projected_local_hours must be present and non-negative; got {rb.get('projected_local_hours')!r}"
    assert rb["projected_local_hours"] >= 0.0, msg_local
    msg_cloud = f"projected_cloud_c3_hours must be present and non-negative; got {rb.get('projected_cloud_c3_hours')!r}"
    assert rb["projected_cloud_c3_hours"] >= 0.0, msg_cloud


# ---------------------------------------------------------------------------
# 14: false-negative risk quantified
# ---------------------------------------------------------------------------


def test_false_negative_risk_quantified(report: dict[str, Any]) -> None:
    fnr = report["false_negative_risk"]
    assert isinstance(fnr, dict), "false_negative_risk must be an object"
    for key in ("at_capped_budget", "at_n_min"):
        v = fnr[key]
        msg = f"false_negative_risk[{key!r}] must be a probability in [0,1]; got {v!r}"
        assert isinstance(v, (int, float)) and 0.0 <= v <= 1.0, msg


# ---------------------------------------------------------------------------
# 15: refusal rule present verbatim
# ---------------------------------------------------------------------------


def test_refusal_rule_present_verbatim(report: dict[str, Any]) -> None:
    rr = report["refusal_rule"]
    msg_type = f"refusal_rule must be a non-empty string; got {type(rr).__name__}"
    assert isinstance(rr, str) and rr.strip(), msg_type
    msg_content = "refusal_rule must encode the fail-closed POWER_GATE_REFUSED_UNDERPOWERED rule"
    assert "POWER_GATE_REFUSED_UNDERPOWERED" in rr and "feasible_cap_n_seeds" in rr, msg_content
    msg_nofudge = "refusal_rule must explicitly forbid loosening alpha / inflating the effect prior"
    assert "NEVER loosens alpha" in rr or "never loosens alpha" in rr.lower(), msg_nofudge


# ---------------------------------------------------------------------------
# 16: decision matches the canonical_run_authorized flag
# ---------------------------------------------------------------------------


def test_decision_matches_canonical_run_authorized_flag(
    report: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    dec = report["decision"]
    auth = report["canonical_run_authorized"]
    if dec == "POWER_GATE_PASS":
        assert auth is True, "PASS must imply canonical_run_authorized=True"
    elif dec == "POWER_GATE_REFUSED_UNDERPOWERED":
        assert auth is False, "REFUSED must imply canonical_run_authorized=False"
    else:
        assert dec == "POWER_GATE_INVALID", f"unexpected decision {dec!r}"
        assert auth is False, "INVALID must imply canonical_run_authorized=False"
    msg_sum = "summary decision/authorized must agree with the report"
    assert summary["decision"] == dec and summary["canonical_run_authorized"] == auth, msg_sum


# ---------------------------------------------------------------------------
# 17: underpowered cells listed if any
# ---------------------------------------------------------------------------


def test_underpowered_cells_listed_if_any(report: dict[str, Any]) -> None:
    cap = report["feasible_cap_n_seeds"]
    expected_under = [c for c in report["per_cell"] if c["n_min"] > cap]
    listed = report["underpowered_cells"]
    msg_count = (
        f"underpowered_cells count {len(listed)} must equal the number of "
        f"per_cell entries with n_min > feasible_cap {len(expected_under)}"
    )
    assert len(listed) == len(expected_under), msg_count
    if report["decision"] == "POWER_GATE_REFUSED_UNDERPOWERED":
        msg_nonempty = "a REFUSED_UNDERPOWERED verdict must list >=1 underpowered cell"
        assert len(listed) >= 1, msg_nonempty


# ---------------------------------------------------------------------------
# 18: P7 designs, does NOT run a canonical sweep
# ---------------------------------------------------------------------------


def test_no_canonical_run_executed(report: dict[str, Any], summary: dict[str, Any]) -> None:
    msg_r = "report must assert no_canonical_run_executed=True"
    assert report["no_canonical_run_executed"] is True, msg_r
    msg_s = "summary must assert no_canonical_run_executed=True"
    assert summary["no_canonical_run_executed"] is True, msg_s
    msg_data = "report must assert no_real_data=True (P7 is design-only)"
    assert report["no_real_data"] is True, msg_data


# ---------------------------------------------------------------------------
# 19: D-002I n_min anchor referenced
# ---------------------------------------------------------------------------


def test_d002i_n_min_anchor_referenced(report: dict[str, Any]) -> None:
    anchor = report["d002i_n_min_anchor"]
    msg = f"d002i_n_min_anchor must reference the D-002I median ~=93; got {anchor!r}"
    assert anchor == 93, msg
    note = report["d002i_anchor_note"]
    msg_note = "d002i_anchor_note must mention the D-002I diagnosis tie-point"
    assert isinstance(note, str) and "D-002I" in note and "93" in note, msg_note
    just = report["feasible_cap_justification"]
    msg_just = (
        "feasible_cap_justification must anchor the cap to the D-002I median and D-002H budget"
    )
    assert "D-002I" in just and "D-002H" in just, msg_just


# ---------------------------------------------------------------------------
# 20: no D-002J prereg edit
# ---------------------------------------------------------------------------


def test_no_d002j_prereg_edit() -> None:
    prereg = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
    msg_exists = f"D-002J prereg must exist unchanged at {prereg}"
    assert prereg.is_file(), msg_exists
    import hashlib

    actual = hashlib.sha256(prereg.read_bytes()).hexdigest()
    expected = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"
    msg_sha = f"D-002J prereg sha must be byte-exact UNCHANGED; got {actual}"
    assert actual == expected, msg_sha


# ---------------------------------------------------------------------------
# 21: no unauthorized research/systemic_risk edit (P7 tools/, not research/)
# ---------------------------------------------------------------------------


def test_no_research_systemic_risk_unauthorized_edit() -> None:
    # P7 adds tooling under tools/systemic_risk/, NOT research/systemic_risk/.
    engine = REPO_ROOT / "tools/systemic_risk/design_d002j_power_grid.py"
    msg_engine = f"P7 power engine must live under tools/systemic_risk/; missing {engine}"
    assert engine.is_file(), msg_engine
    p7_research = REPO_ROOT / "research/systemic_risk/power"
    msg_noresearch = "P7 must NOT create research/systemic_risk/power/* (tools/ only)"
    assert not p7_research.exists(), msg_noresearch


# ---------------------------------------------------------------------------
# 22: no unresolved merge markers in P7-touching files
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        REPO_ROOT / "tools/systemic_risk/design_d002j_power_grid.py",
        REPO_ROOT / "tests/systemic_risk/test_d002j_power_first_gate.py",
        REPORT_PATH,
        SUMMARY_PATH,
        REPO_ROOT / "artifacts/governance/verdicts/d002j_p7_verdict_v1.json",
        REPO_ROOT / "docs/research/D002J_POWER_FIRST_REPORT.md",
    ]
    hits: list[tuple[str, int]] = []
    for p in targets:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i))
    msg = f"unresolved git-merge markers detected: {hits}"
    assert hits == [], msg


# ---------------------------------------------------------------------------
# Extra engine-unit guards (formula sanity; not artifact reads)
# ---------------------------------------------------------------------------


def test_engine_power_formula_inverts() -> None:
    # n_min and mde are inverses: at n = n_min the MDE must be <= the
    # effect it was sized for (monotone, exact-ish round trip).
    alpha = 0.05 / 102
    d = 0.5
    nm = n_min(d, alpha, 0.8)
    achieved_mde = mde(alpha, 0.8, nm)
    msg = f"MDE at n_min ({achieved_mde:.4f}) must be <= the sized effect ({d})"
    assert achieved_mde <= d + 1e-9, msg


def test_bonferroni_denominator_helper_is_product() -> None:
    msg = "bonferroni_denominator must be the 4-axis product"
    assert bonferroni_denominator(3, 7, 3, 2) == 126, msg
    with pytest.raises(ValueError):
        bonferroni_denominator(0, 1, 1, 1)


def test_effect_size_prior_rejects_missing_pc(tmp_path: Path) -> None:
    # A PC manifest with no families must fail closed (no fabrication).
    bad: dict[str, Any] = {"control_families": []}
    with pytest.raises((ValueError, KeyError)):
        effect_size_prior(bad)


def test_run_power_design_deterministic_decision() -> None:
    # With a fixed per-sim cost the decision/cell-count is deterministic.
    d1 = run_power_design(per_sim_seconds=5e-5)
    d2 = run_power_design(per_sim_seconds=5e-5)
    msg = "fixed-probe power design must be decision-deterministic across runs"
    assert d1.decision.decision == d2.decision.decision, msg
    assert d1.bonferroni_denominator == d2.bonferroni_denominator, msg
    assert len(d1.cells) == len(d2.cells), msg
