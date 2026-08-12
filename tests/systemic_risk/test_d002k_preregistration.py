# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P0 pre-registration guard suite.

D-002K is a FRESH lineage opened AFTER the D-002J-P7
``POWER_GATE_REFUSED_UNDERPOWERED`` terminal verdict (PR #705, merge sha
``c5c4158bed639014ec35ab8f53ec70d98be660a2``). It inherits the
``effect_too_small`` refusal axis as a documented PARENT FAILURE and is
explicitly designed against it by narrowing SCOPE (3 windows x 1
mechanism x 1 primary metric), NOT by loosening the STATISTICS at a
fixed hypothesis count.

Every test in this module guards one structural invariant of the
D-002K pre-registration. The suite fails closed if any future PR:

* mutates D-002J (its prereg / P7 capsule / power_summary must be
  byte-exact frozen),
* relaxes alpha or inflates the effect prior,
* promotes D-002K to a D-002J rescue,
* fails to lock the single primary metric / matched-placebo policy /
  power-gate-before-scoring law before any run.

D-002J stays REFUSED. That is the honest foundation D-002K is built on.
This module is governance infra -- it imports no physics, runs no
canonical sweep, promotes no claim.

All multi-line asserts use the msg-var idiom (``msg = ...`` extracted
above the ``assert``) so the module renders byte-identically under both
black and ruff-format, which disagree on the parenthesised-message
style (mirrors ``tests/governance/test_verdict_dag_integrity.py``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Anchors / constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"
FAILURE_AXIS_JSON: Path = (
    REPO_ROOT / "artifacts/d002k/prereg/d002k_failure_axis_inheritance_v1.json"
)
PRIMARY_METRIC_JSON: Path = (
    REPO_ROOT / "artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json"
)
P0_VERDICT_JSON: Path = REPO_ROOT / "artifacts/governance/verdicts/d002k_p0_verdict_v1.json"
DAG_VERDICT_JSON: Path = REPO_ROOT / "artifacts/governance/verdicts/d002j_verdict_dag_v1.json"

PARENT_REFUSAL_SHA: str = "c5c4158bed639014ec35ab8f53ec70d98be660a2"
D002J_PREREG_SHA: str = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"

# The 6 locked governance anchors (D-002C/G/G/H/I/J), byte-exact.
LOCKED_GOVERNANCE_SHAS: dict[str, str] = {
    "docs/governance/D002C_CLAIM_LEDGER.yaml": (
        "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"
    ),
    "docs/governance/D002G_PREREGISTRATION.yaml": (
        "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04"
    ),
    "docs/governance/D002G_ACCEPTANCE_RULES.md": (
        "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"
    ),
    "docs/governance/D002H_PREREGISTRATION.yaml": (
        "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"
    ),
    "docs/governance/D002I_PREREGISTRATION.yaml": (
        "b646989c032dc0e29f9b791e0b68209ff22b40f4757737712badc8656cf2db5f"
    ),
    "docs/governance/D002J_PREREGISTRATION.yaml": D002J_PREREG_SHA,
}

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _load_prereg() -> dict[str, Any]:
    with PREREG_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    msg = f"prereg must parse to a mapping; got {type(data).__name__}"
    assert isinstance(data, dict), msg
    return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    msg = f"{path} must be a JSON object; got {type(data).__name__}"
    assert isinstance(data, dict), msg
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. Prereg exists + schema
# ---------------------------------------------------------------------------


def test_d002k_prereg_exists() -> None:
    msg_file = f"D-002K prereg missing: {PREREG_PATH}"
    assert PREREG_PATH.is_file(), msg_file
    text = PREREG_PATH.read_text(encoding="utf-8")
    assert text.strip(), "D-002K prereg must not be empty"
    assert "study_id: D-002K" in text, "prereg must declare study_id D-002K"


def test_d002k_prereg_schema_version() -> None:
    prereg = _load_prereg()
    msg_schema = f"schema_version must be D002K-PREREG-v1; got {prereg['schema_version']!r}"
    assert prereg["schema_version"] == "D002K-PREREG-v1", msg_schema
    msg_study = f"study_id must be D-002K; got {prereg['study_id']!r}"
    assert prereg["study_id"] == "D-002K", msg_study


# ---------------------------------------------------------------------------
# 2. Parent lineage = D-002J terminally refused
# ---------------------------------------------------------------------------


def test_parent_lineage_is_d002j() -> None:
    prereg = _load_prereg()
    msg_lin = f"parent_lineage must be D-002J; got {prereg['parent_lineage']!r}"
    assert prereg["parent_lineage"] == "D-002J", msg_lin
    msg_pr = f"parent_refusal_pr must be 705; got {prereg['parent_refusal_pr']!r}"
    assert prereg["parent_refusal_pr"] == 705, msg_pr
    msg_sha = (
        f"parent_refusal_merge_sha must pin {PARENT_REFUSAL_SHA}; "
        f"got {prereg['parent_refusal_merge_sha']!r}"
    )
    assert prereg["parent_refusal_merge_sha"] == PARENT_REFUSAL_SHA, msg_sha


def test_parent_status_terminal_refused() -> None:
    prereg = _load_prereg()
    msg_status = f"parent_status must be TERMINAL_REFUSED; got {prereg['parent_status']!r}"
    assert prereg["parent_status"] == "TERMINAL_REFUSED", msg_status
    msg_dec = (
        f"parent_refusal_decision must be POWER_GATE_REFUSED_UNDERPOWERED; "
        f"got {prereg['parent_refusal_decision']!r}"
    )
    assert prereg["parent_refusal_decision"] == "POWER_GATE_REFUSED_UNDERPOWERED", msg_dec


# ---------------------------------------------------------------------------
# 3. Inherited failure axis + no-rescue
# ---------------------------------------------------------------------------


def test_inherited_failure_axis_is_effect_too_small() -> None:
    prereg = _load_prereg()
    msg_pre = (
        f"inherited_failure_axis must be effect_too_small; got {prereg['inherited_failure_axis']!r}"
    )
    assert prereg["inherited_failure_axis"] == "effect_too_small", msg_pre
    fa = _load_json(FAILURE_AXIS_JSON)
    _amsg1 = "failure-axis JSON must also pin effect_too_small"
    assert fa["inherited_failure_axis"] == "effect_too_small", _amsg1


def test_is_rescue_false() -> None:
    prereg = _load_prereg()
    msg_pre = f"is_rescue must be False; got {prereg['is_rescue']!r}"
    assert prereg["is_rescue"] is False, msg_pre
    fa = _load_json(FAILURE_AXIS_JSON)
    assert fa["is_rescue"] is False, "failure-axis JSON is_rescue must be False"


def test_no_rescue_boundary_nonempty() -> None:
    prereg = _load_prereg()
    boundary = prereg["no_rescue_boundary"]
    _amsg2 = "no_rescue_boundary must be a non-empty string"
    assert isinstance(boundary, str) and boundary.strip(), _amsg2
    low = boundary.lower()
    msg_deny = f"no_rescue_boundary must explicitly deny reopening/rescue; got {boundary!r}"
    assert "does not" in low or "not reopen" in low, msg_deny
    assert "refused" in low, "no_rescue_boundary must reference the D-002J REFUSED state"


# ---------------------------------------------------------------------------
# 4. Locked mechanism / windows / metric
# ---------------------------------------------------------------------------


def test_primary_mechanism_is_funding_liquidity_rollover() -> None:
    prereg = _load_prereg()
    msg_mech = (
        f"primary_mechanism must be funding_liquidity_rollover; got {prereg['primary_mechanism']!r}"
    )
    assert prereg["primary_mechanism"] == "funding_liquidity_rollover", msg_mech
    rationale = prereg["primary_mechanism_rationale"]
    _amsg3 = "primary_mechanism_rationale must be a non-empty string"
    assert isinstance(rationale, str) and rationale.strip(), _amsg3


def test_primary_windows_exactly_cw3_cw4_cw5() -> None:
    prereg = _load_prereg()
    windows = list(prereg["primary_windows"])
    expected = [
        "CW3_US_REPO_SPIKE_2019",
        "CW4_COVID_DASH_FOR_CASH_2020",
        "CW5_UK_GILT_LDI_2022",
    ]
    msg_w = f"primary_windows must be exactly {expected}; got {windows}"
    assert windows == expected, msg_w
    msg_n = f"exactly 3 primary windows; got {len(windows)}"
    assert len(windows) == 3, msg_n


def test_primary_metric_locked_single() -> None:
    prereg = _load_prereg()
    msg_m = (
        f"primary_metric must be pre_post_standardized_mean_shift; got {prereg['primary_metric']!r}"
    )
    assert prereg["primary_metric"] == "pre_post_standardized_mean_shift", msg_m
    contract = _load_json(PRIMARY_METRIC_JSON)
    assert contract["is_single_primary"] is True, "metric contract must mark single primary"
    msg_n = f"exactly ONE primary metric; got {contract['n_primary_metrics']!r}"
    assert contract["n_primary_metrics"] == 1, msg_n


def test_secondary_metrics_marked_exploratory() -> None:
    prereg = _load_prereg()
    msg_s = (
        f"secondary_metrics_status must be exploratory_only; "
        f"got {prereg['secondary_metrics_status']!r}"
    )
    assert prereg["secondary_metrics_status"] == "exploratory_only", msg_s
    contract = _load_json(PRIMARY_METRIC_JSON)
    _amsg4 = "metric contract must also mark secondary metrics exploratory_only"
    assert contract["secondary_metrics_status"] == "exploratory_only", _amsg4
    _amsg5 = "at least two secondary metrics must be enumerated as exploratory"
    assert len(prereg["secondary_metrics"]) >= 2, _amsg5


# ---------------------------------------------------------------------------
# 5. Matched-placebo + power-gate policy
# ---------------------------------------------------------------------------


def test_matched_placebo_policy_locked_before_scoring() -> None:
    prereg = _load_prereg()
    policy = prereg["matched_placebo_policy"]
    _amsg6 = "matched_placebo_policy.locked_before_scoring must be True"
    assert policy["locked_before_scoring"] is True, _amsg6
    msg_sel = (
        f"placebo selection must be deterministic_pre_registered_algorithm; "
        f"got {policy['selection']!r}"
    )
    assert policy["selection"] == "deterministic_pre_registered_algorithm", msg_sel
    _amsg_npc = "n_placebo_per_crisis must be a locked int"
    assert isinstance(policy["n_placebo_per_crisis"], int), _amsg_npc


def test_power_gate_policy_must_run_before_scoring() -> None:
    prereg = _load_prereg()
    pg = prereg["power_gate_policy"]
    _amsg7 = "power_gate_policy.must_run_before_any_scoring must be True"
    assert pg["must_run_before_any_scoring"] is True, _amsg7
    msg_pt = f"power_target must be 0.8; got {pg['power_target']!r}"
    assert pg["power_target"] == 0.8, msg_pt


def test_alpha_policy_not_relaxed_vs_d002j() -> None:
    prereg = _load_prereg()
    alpha = prereg["power_gate_policy"]["alpha_policy"]
    msg_fam = f"alpha family must be bonferroni; got {alpha['family']!r}"
    assert alpha["family"] == "bonferroni", msg_fam
    msg_rule = (
        f"denominator_rule must be 'n_windows * n_primary_metrics'; "
        f"got {alpha['denominator_rule']!r}"
    )
    assert alpha["denominator_rule"] == "n_windows * n_primary_metrics", msg_rule
    note = alpha["note"].lower()
    assert "narrow" in note, "alpha note must justify the denominator as narrow BY DESIGN"
    _amsg_alpha = "alpha note must explicitly deny loosening/relaxing alpha at fixed scope"
    assert "not" in note and ("loosen" in note or "relax" in note), _amsg_alpha


# ---------------------------------------------------------------------------
# 6. Authorisation gates closed
# ---------------------------------------------------------------------------


def test_canonical_run_authorized_false() -> None:
    prereg = _load_prereg()
    _amsg8 = "canonical_run_authorized must be False at pre-registration"
    assert prereg["canonical_run_authorized"] is False, _amsg8
    assert prereg["benchmark_only"] is True, "benchmark_only must be True"
    _amsg9 = "requires_power_first_approval must be True"
    assert prereg["requires_power_first_approval"] is True, _amsg9


def test_no_canonical_run_authorized() -> None:
    prereg = _load_prereg()
    assert prereg["canonical_run_authorized"] is False, "prereg canonical_run_authorized False"
    fa = _load_json(FAILURE_AXIS_JSON)
    contract = _load_json(PRIMARY_METRIC_JSON)
    assert fa["canonical_run_authorized"] is False, "failure-axis JSON canonical_run False"
    assert contract["canonical_run_authorized"] is False, "metric contract canonical_run False"
    dag = _load_json(DAG_VERDICT_JSON)
    _amsg10 = "DAG canonical_run_authorized_anywhere must stay False"
    assert dag["canonical_run_authorized_anywhere"] is False, _amsg10


# ---------------------------------------------------------------------------
# 7. Forbidden claims
# ---------------------------------------------------------------------------


def test_forbidden_claims_include_no_d002j_rescue() -> None:
    prereg = _load_prereg()
    forbidden = list(prereg["forbidden_claims"])
    msg_r = f"forbidden_claims must include the no-rescue claim; got {forbidden}"
    assert "D-002K rescues D-002J" in forbidden, msg_r
    msg_rev = f"forbidden_claims must forbid reversing D-002J-P7 REFUSED; got {forbidden}"
    assert "D-002K reverses D-002J-P7 REFUSED" in forbidden, msg_rev


def test_forbidden_claims_include_no_relaxed_alpha() -> None:
    prereg = _load_prereg()
    forbidden = list(prereg["forbidden_claims"])
    msg_a = f"forbidden_claims must forbid relaxed-alpha justification; got {forbidden}"
    assert "relaxed alpha is justified by D-002J refusal" in forbidden, msg_a
    allowed = list(prereg["allowed_claims"])
    msg_t = f"allowed_claims must keep D-002J REFUSED truthful; got {allowed}"
    assert "D-002J remains the truthful terminal REFUSED verdict" in allowed, msg_t


# ---------------------------------------------------------------------------
# 8. Failure-axis inheritance JSON pins the D-002J-P7 sha + distribution
# ---------------------------------------------------------------------------


def test_failure_axis_inheritance_json_pins_d002j_p7_sha() -> None:
    fa = _load_json(FAILURE_AXIS_JSON)
    msg_s = f"schema must be D002K-FAILURE-AXIS-INHERITANCE-v1; got {fa['schema_version']!r}"
    assert fa["schema_version"] == "D002K-FAILURE-AXIS-INHERITANCE-v1", msg_s
    msg_sha = (
        f"failure-axis JSON must pin {PARENT_REFUSAL_SHA}; got {fa['parent_refusal_merge_sha']!r}"
    )
    assert fa["parent_refusal_merge_sha"] == PARENT_REFUSAL_SHA, msg_sha
    assert fa["parent_refusal_pr"] == 705, "failure-axis JSON must pin parent_refusal_pr 705"
    dist = fa["d002j_p7_n_min_distribution"]
    msg_d = f"d002j_p7_n_min_distribution must copy D-002J power_summary; got {dist}"
    assert dist == {"min": 150, "median": 235, "max": 417}, msg_d
    msg_b = f"d002j_bonferroni_denominator must be 102; got {fa['d002j_bonferroni_denominator']!r}"
    assert fa["d002j_bonferroni_denominator"] == 102, msg_b


def test_primary_metric_contract_json_valid() -> None:
    contract = _load_json(PRIMARY_METRIC_JSON)
    msg_s = f"schema must be D002K-PRIMARY-METRIC-CONTRACT-v1; got {contract['schema_version']!r}"
    assert contract["schema_version"] == "D002K-PRIMARY-METRIC-CONTRACT-v1", msg_s
    msg_m = f"primary_metric_id must match prereg; got {contract['primary_metric_id']!r}"
    assert contract["primary_metric_id"] == "pre_post_standardized_mean_shift", msg_m
    assert contract["locked_before_any_run"] is True, "locked_before_any_run must be True"
    steps = contract["computation_steps"]
    _amsg11 = "computation_steps must enumerate the exact computation (>=3 steps)"
    assert isinstance(steps, list) and len(steps) >= 3, _amsg11
    # Threshold VALUE must NOT be locked here (power-gate territory).
    semantics = contract["decision_threshold_semantics"].lower()
    _amsg12 = "decision_threshold_semantics must defer the threshold value to the power gate"
    assert "power-gate" in semantics or "power gate" in semantics, _amsg12


# ---------------------------------------------------------------------------
# 9. D-002J byte-exact frozen
# ---------------------------------------------------------------------------


def test_d002j_artifacts_byte_exact_unchanged() -> None:
    prereg_path = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
    msg_f = f"D-002J prereg missing: {prereg_path}"
    assert prereg_path.is_file(), msg_f
    actual = _sha256(prereg_path)
    msg_sha = f"D-002J prereg sha drifted; expected {D002J_PREREG_SHA}, got {actual}"
    assert actual == D002J_PREREG_SHA, msg_sha
    p7 = _load_json(REPO_ROOT / "artifacts/governance/verdicts/d002j_p7_verdict_v1.json")
    msg_st = f"D-002J-P7 must stay TERMINAL_REFUSED; got {p7['status']!r}"
    assert p7["status"] == "TERMINAL_REFUSED", msg_st
    msg_de = f"D-002J-P7 decision must stay POWER_GATE_REFUSED_UNDERPOWERED; got {p7['decision']!r}"
    assert p7["decision"] == "POWER_GATE_REFUSED_UNDERPOWERED", msg_de
    psum = _load_json(REPO_ROOT / "artifacts/d002j/power/power_summary_v1.json")
    msg_ax = (
        f"D-002J power_summary refused_axis must stay effect_too_small; "
        f"got {psum['refused_axis']!r}"
    )
    assert psum["refused_axis"] == "effect_too_small", msg_ax
    msg_md = (
        f"D-002J power_summary n_min median must stay 235.0; "
        f"got {psum['n_min_distribution']['median']!r}"
    )
    assert psum["n_min_distribution"]["median"] == 235.0, msg_md


def test_locked_governance_shas_byte_exact() -> None:
    mismatches: list[tuple[str, str, str]] = []
    for rel, expected in LOCKED_GOVERNANCE_SHAS.items():
        path = REPO_ROOT / rel
        msg_p = f"locked governance file missing: {path}"
        assert path.is_file(), msg_p
        actual = _sha256(path)
        if actual != expected:
            mismatches.append((rel, expected, actual))
    msg_drift = f"locked governance sha drift: {mismatches}"
    assert not mismatches, msg_drift
    msg_n = f"exactly 6 locked governance anchors; got {len(LOCKED_GOVERNANCE_SHAS)}"
    assert len(LOCKED_GOVERNANCE_SHAS) == 6, msg_n


# ---------------------------------------------------------------------------
# 10. P0 verdict capsule + DAG node
# ---------------------------------------------------------------------------


def test_d002k_p0_verdict_capsule_locked() -> None:
    cap = _load_json(P0_VERDICT_JSON)
    msg_id = f"node_id must be D002K-P0; got {cap['node_id']!r}"
    assert cap["node_id"] == "D002K-P0", msg_id
    msg_d = f"decision must be D002K_PREREG_LOCKED; got {cap['decision']!r}"
    assert cap["decision"] == "D002K_PREREG_LOCKED", msg_d
    msg_st = f"status must be TERMINAL_PASS; got {cap['status']!r}"
    assert cap["status"] == "TERMINAL_PASS", msg_st
    msg_par = (
        f"parent_nodes must be ['D002J-P7'] (descends from the refusal); "
        f"got {cap['parent_nodes']!r}"
    )
    assert cap["parent_nodes"] == ["D002J-P7"], msg_par
    msg_an = f"allowed_next_nodes must be ['D002K-P1']; got {cap['allowed_next_nodes']!r}"
    assert cap["allowed_next_nodes"] == ["D002K-P1"], msg_an
    msg_fn = (
        f"forbidden_next_nodes must include D002J-P8 (no D-002J P8 enablement); "
        f"got {cap['forbidden_next_nodes']!r}"
    )
    assert "D002J-P8" in cap["forbidden_next_nodes"], msg_fn
    _amsg13 = "failure_retention must be null for a TERMINAL_PASS capsule"
    assert cap["failure_retention"] is None, _amsg13


def test_dag_has_d002k_p0_and_d002j_p7_still_refused() -> None:
    dag = _load_json(DAG_VERDICT_JSON)
    # D-002K-P4 (power-first gate) advanced the DAG snapshot: 15 nodes,
    # topo tail D002K-P4. P4 honestly REFUSED
    # (POWER_GATE_REFUSED_UNDERPOWERED, TERMINAL_REFUSED) so the lineage
    # halts: next_legal is empty and D002K-P4 joins D002J-P1A/D002J-P7
    # in rejected_nodes_retained. D-002K-P0/P1/P2/P3 remain present;
    # D-002J-P7/P1A stay refused/rejected retained. Same sanctioned
    # per-phase widen.
    msg_n = f"DAG must have 15 nodes; got {dag['nodes_count']!r}"
    assert dag["nodes_count"] == 15, msg_n
    msg_p0 = f"D002K-P0 must remain in topological_order; got {dag['topological_order']!r}"
    assert "D002K-P0" in dag["topological_order"], msg_p0
    msg_p1 = f"D002K-P1 must remain in topological_order; got {dag['topological_order']!r}"
    assert "D002K-P1" in dag["topological_order"], msg_p1
    msg_p2 = f"D002K-P2 must remain in topological_order; got {dag['topological_order']!r}"
    assert "D002K-P2" in dag["topological_order"], msg_p2
    msg_p3 = f"D002K-P3 must remain in topological_order; got {dag['topological_order']!r}"
    assert "D002K-P3" in dag["topological_order"], msg_p3
    msg_to = (
        f"D002K-P4 must be appended last in topological_order; got {dag['topological_order']!r}"
    )
    assert dag["topological_order"][-1] == "D002K-P4", msg_to
    _amsg14 = "D002J-P7 must remain in rejected_nodes_retained (still refused)"
    assert "D002J-P7" in dag["rejected_nodes_retained"], _amsg14
    _amsg15 = "D002J-P1A must remain in rejected_nodes_retained"
    assert "D002J-P1A" in dag["rejected_nodes_retained"], _amsg15
    _amsg16 = "D002K-P4 must be in rejected_nodes_retained (honestly refused)"
    assert "D002K-P4" in dag["rejected_nodes_retained"], _amsg16
    msg_nl = (
        f"P4 REFUSED halts the lineage: next_legal must be empty; "
        f"got {dag['next_legal_nodes_from_main_head']!r}"
    )
    assert dag["next_legal_nodes_from_main_head"] == [], msg_nl
    lt = dag["lineage_transitions"]["D002J-P7"]
    msg_ls = f"lineage_transition D002J-P7 status must be TERMINAL_REFUSED; got {lt['status']!r}"
    assert lt["status"] == "TERMINAL_REFUSED", msg_ls
    msg_sl = f"lineage_transition successor_lineage must be D-002K; got {lt['successor_lineage']!r}"
    assert lt["successor_lineage"] == "D-002K", msg_sl
    assert lt["is_rescue"] is False, "lineage_transition is_rescue must be False"


# ---------------------------------------------------------------------------
# 11. Stop conditions + no merge markers
# ---------------------------------------------------------------------------


def test_stop_conditions_locked() -> None:
    prereg = _load_prereg()
    stops = list(prereg["stop_conditions"])
    msg_n = f"at least 3 stop conditions; got {len(stops)}"
    assert len(stops) >= 3, msg_n
    joined = " | ".join(stops).lower()
    _amsg16 = "a stop condition must require a fresh D-002L on power-gate REFUSE"
    assert "refuses" in joined and "d-002l" in joined, _amsg16
    _amsg17 = "a stop condition must invalidate an unlocked primary metric"
    assert "primary metric not locked" in joined, _amsg17


def test_no_unresolved_merge_markers() -> None:
    targets = [
        PREREG_PATH,
        FAILURE_AXIS_JSON,
        PRIMARY_METRIC_JSON,
        P0_VERDICT_JSON,
        DAG_VERDICT_JSON,
        REPO_ROOT / "docs/research/D002K_DESIGN_RATIONALE.md",
        REPO_ROOT / "docs/research/D002J_LINEAGE_MAP.md",
        REPO_ROOT / "docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md",
    ]
    hits: list[tuple[str, int, str]] = []
    for p in targets:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i, line[:32]))
    msg = f"unresolved git-merge markers detected: {hits}"
    assert hits == [], msg
