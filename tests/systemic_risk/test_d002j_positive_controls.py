# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P4 — planted positive controls v1 guard tests.

>= 18 P4 guard tests. Every test contains >= 2 assertions or >= 2
distinct cases. Tests 11-16 actually SYNTHESISE control instances and
verify ``score(signal) >= pass_threshold``. Test 17 explicitly verifies
every negative sibling scores BELOW pass_threshold (rejection
discipline). PC5 (test 15) is INVERTED: pass = the lookahead is caught.

P4 is SYNTHETIC: no real data, no substrate, no null execution, no
canonical run, no D-002J prereg edit, no promotion to a real-world
performance claim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from research.systemic_risk.d002j_positive_controls import (
    ALL_FAMILIES,
    ALL_SPECS,
    PC5_FAIL_TOKEN,
    PC5_PASS_TOKEN,
    PC5InfoDelayLeakageTrap,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
PC_DIR: Path = REPO_ROOT / "artifacts" / "d002j" / "positive_controls"
MANIFEST_JSON: Path = PC_DIR / "positive_control_manifest_v1.json"
SUMMARY_JSON: Path = PC_DIR / "positive_control_summary_v1.json"
PROTOCOL_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_POSITIVE_CONTROL_PROTOCOL.md"
P4_CAPSULE_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_p4_verdict_v1.json"
)
DAG_VERDICT_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_verdict_dag_v1.json"
)
D002J_PREREG: Path = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"
IMPL_PY: Path = REPO_ROOT / "research" / "systemic_risk" / "d002j_positive_controls.py"

SEED_BATTERY: tuple[int, ...] = (42, 7, 123, 999, 2026, 1, 55, 314)
_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _load_manifest() -> dict[str, Any]:
    with MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _families() -> dict[str, Any]:
    return {spec.family_id: (cls, spec) for cls, spec in zip(ALL_FAMILIES, ALL_SPECS)}


# ---------------------------------------------------------------------------
# 1-2 artifact existence
# ---------------------------------------------------------------------------


def test_positive_control_manifest_exists() -> None:
    assert MANIFEST_JSON.is_file(), f"missing manifest: {MANIFEST_JSON}"
    data = _load_manifest()
    assert data["schema_version"] == "D002J-POSITIVE-CONTROL-MANIFEST-v1", data["schema_version"]


def test_summary_exists() -> None:
    assert SUMMARY_JSON.is_file(), f"missing summary: {SUMMARY_JSON}"
    with SUMMARY_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["schema_version"] == "D002J-POSITIVE-CONTROL-SUMMARY-v1", data["schema_version"]
    assert data["decision"] == "POSITIVE_CONTROLS_READY", data["decision"]


# ---------------------------------------------------------------------------
# 3 six families present
# ---------------------------------------------------------------------------


def test_six_control_families_present() -> None:
    manifest = _load_manifest()
    fams = manifest["control_families"]
    assert len(fams) == 6, f"expected 6 control families, got {len(fams)}"
    assert len(ALL_FAMILIES) == 6, f"expected 6 implemented families, got {len(ALL_FAMILIES)}"
    classes = sorted(e["control_class"] for e in fams)
    expected = sorted(
        [
            "liquidity_shock",
            "contagion_cascade",
            "balance_sheet_impairment",
            "volatility_regime_switch",
            "information_delay_trap",
            "official_response_event_shock",
        ]
    )
    assert classes == expected, f"control_class mismatch: {classes} vs {expected}"


# ---------------------------------------------------------------------------
# 4-9 per-family metadata discipline
# ---------------------------------------------------------------------------


def test_each_family_has_negative_sibling() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        sib = e["negative_sibling_id"]
        assert isinstance(sib, str) and sib.strip(), e
        assert "NEGATIVE_SIBLING" in sib, f"{e['control_family_id']} sibling id {sib!r}"
    assert manifest["negative_siblings_required"] is True


def test_each_family_has_ground_truth_metadata() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        gtf = e["ground_truth_fields"]
        assert isinstance(gtf, list) and len(gtf) >= 2, f"{e['control_family_id']} gt fields {gtf}"
        time_anchors = {"onset_time", "switch_time", "leakage_delta", "intervention_time"}
        assert time_anchors & set(gtf), f"{e['control_family_id']} lacks a time-anchor field: {gtf}"


def test_each_family_has_pass_threshold() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        pt = e["pass_threshold"]
        assert isinstance(pt["value"], (int, float)), f"{e['control_family_id']} {pt}"
        assert pt["value"] > 0, f"{e['control_family_id']} pass_threshold must be >0: {pt}"


def test_each_family_has_fail_threshold() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        ft = e["fail_threshold"]
        assert isinstance(ft["value"], (int, float)), f"{e['control_family_id']} {ft}"
        assert ft["interpretation"] == "FALSE_POSITIVE", f"{e['control_family_id']} {ft}"


def test_each_family_has_expected_observable_signature() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        sig = e["expected_observable_signature"]
        assert isinstance(sig, str) and len(sig) >= 20, f"{e['control_family_id']} {sig!r}"
        assert e["seed_policy"].startswith("deterministic"), e["seed_policy"]


def test_each_family_has_forbidden_claim_boundary() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        fcb = e["forbidden_claim_boundary"].lower()
        assert "synthetic" in fcb, f"{e['control_family_id']} {fcb!r}"
        assert "canonical run" in fcb, f"{e['control_family_id']} {fcb!r}"


# ---------------------------------------------------------------------------
# 10 determinism
# ---------------------------------------------------------------------------


def test_seed_policy_deterministic_for_each_family() -> None:
    for cls, _spec in zip(ALL_FAMILIES, ALL_SPECS):
        fam = cls()
        a = fam.generate(seed=42, params={})
        b = fam.generate(seed=42, params={})
        msg_sig = f"{cls.family_id} signal nondeterm"
        assert np.array_equal(a.signal_array, b.signal_array), msg_sig
        msg_null = f"{cls.family_id} null nondeterm"
        assert np.array_equal(a.null_sibling_array, b.null_sibling_array), msg_null


# ---------------------------------------------------------------------------
# 11-16 SIGNAL distinguishable from NULL under pass_threshold
# ---------------------------------------------------------------------------


def _assert_signal_separates_null(cls: Any, spec: Any) -> None:
    fam = cls()
    thr = spec.pass_threshold_value
    sig_scores: list[float] = []
    null_scores: list[float] = []
    for sd in SEED_BATTERY:
        inst = fam.generate(seed=sd, params={})
        sig_scores.append(fam.score(inst.signal_array))
        null_scores.append(fam.score(inst.null_sibling_array))
    assert min(sig_scores) >= thr, (
        f"{spec.family_id} signal must score >= pass_threshold over the seed "
        f"battery; min_signal={min(sig_scores):.4f} thr={thr} scores={sig_scores}"
    )
    assert max(null_scores) < thr, (
        f"{spec.family_id} null sibling MUST score below pass_threshold "
        f"(else FALSE_POSITIVE; do NOT loosen threshold); "
        f"max_null={max(null_scores):.4f} thr={thr} scores={null_scores}"
    )


def test_pc1_signal_distinguishable_from_null_under_pass_threshold() -> None:
    fams = _families()
    _assert_signal_separates_null(*fams["PC1_LIQUIDITY_SHOCK_INJECTION"])


def test_pc2_signal_distinguishable_from_null_under_pass_threshold() -> None:
    fams = _families()
    _assert_signal_separates_null(*fams["PC2_CONTAGION_CASCADE_INJECTION"])


def test_pc3_signal_distinguishable_from_null_under_pass_threshold() -> None:
    fams = _families()
    _assert_signal_separates_null(*fams["PC3_BALANCE_SHEET_IMPAIRMENT_INJECTION"])


def test_pc4_signal_distinguishable_from_null_under_pass_threshold() -> None:
    fams = _families()
    _assert_signal_separates_null(*fams["PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH"])


def test_pc5_lookahead_detector_caught_by_p3_invariant() -> None:
    # INVERTED: pass = the constructed leakage IS caught (score == 1.0)
    # and the point-in-time null sibling is NOT flagged (score == 0.0).
    fam = PC5InfoDelayLeakageTrap()
    for sd in SEED_BATTERY:
        inst = fam.generate(seed=sd, params={})
        leak_caught = fam.score(inst.signal_array)
        pit_clean = fam.score(inst.null_sibling_array)
        msg_leak = (
            f"PC5 must CATCH the planted lookahead violation (release<obs); "
            f"got {leak_caught} at seed={sd}"
        )
        assert leak_caught == PC5_PASS_TOKEN, msg_leak
        msg_pit = (
            f"PC5 point-in-time null sibling must NOT be flagged; got {pit_clean} at seed={sd}"
        )
        assert pit_clean == PC5_FAIL_TOKEN, msg_pit


def test_pc6_signal_distinguishable_from_null_under_pass_threshold() -> None:
    fams = _families()
    _assert_signal_separates_null(*fams["PC6_OFFICIAL_RESPONSE_EVENT_SHOCK"])


# ---------------------------------------------------------------------------
# 17 negative siblings score below pass threshold (rejection discipline)
# ---------------------------------------------------------------------------


def test_negative_siblings_score_below_pass_threshold() -> None:
    # Critical: the pipeline must REJECT every null. Non-inverted
    # families: score(null) < pass_threshold. Inverted PC5: the
    # point-in-time null sibling must score the FAIL token (not caught).
    for cls, spec in zip(ALL_FAMILIES, ALL_SPECS):
        fam = cls()
        for sd in SEED_BATTERY:
            inst = fam.generate(seed=sd, params={})
            null_score = fam.score(inst.null_sibling_array)
            if spec.family_id == "PC5_INFORMATION_DELAY_VINTAGE_LEAKAGE_TRAP":
                assert null_score == PC5_FAIL_TOKEN, (
                    f"PC5 null sibling must score FAIL token (point-in-time "
                    f"correct ⇒ not flagged); got {null_score} seed={sd}"
                )
            else:
                assert null_score < spec.pass_threshold_value, (
                    f"{spec.family_id} negative sibling scored "
                    f"{null_score:.4f} >= pass_threshold "
                    f"{spec.pass_threshold_value} at seed={sd}: FALSE_POSITIVE. "
                    f"Control design broken — do NOT loosen the threshold."
                )


# ---------------------------------------------------------------------------
# 18 P5 substrate mapping
# ---------------------------------------------------------------------------


def test_each_family_maps_to_p5_substrate_candidate() -> None:
    manifest = _load_manifest()
    for e in manifest["control_families"]:
        cands = e["mapped_p5_substrate_candidates"]
        assert isinstance(cands, list) and len(cands) >= 1, f"{e['control_family_id']} {cands}"
        wins = e["mapped_p2_window_class"]
        assert isinstance(wins, list) and len(wins) >= 1, f"{e['control_family_id']} {wins}"


# ---------------------------------------------------------------------------
# 19-22 scope / no-overclaim guards
# ---------------------------------------------------------------------------


def test_no_real_world_performance_claim() -> None:
    manifest_txt = MANIFEST_JSON.read_text(encoding="utf-8").lower()
    summary_txt = SUMMARY_JSON.read_text(encoding="utf-8").lower()
    for txt in (manifest_txt, summary_txt):
        assert "synthetic" in txt, "must declare synthetic-only boundary"
        assert "does not prove real-world" in txt, "must forbid real-world performance claim"


def test_no_bank_level_validation_claim() -> None:
    proto = PROTOCOL_MD.read_text(encoding="utf-8").lower()
    assert "does not prove bank-level validation" in proto, "protocol must forbid bank-level claim"
    manifest = _load_manifest()
    joined = " ".join(e["forbidden_claim_boundary"].lower() for e in manifest["control_families"])
    assert "bank-level validation" in joined, "PC1 boundary must forbid bank-level validation"


def test_no_canonical_run_authorized() -> None:
    with SUMMARY_JSON.open(encoding="utf-8") as fh:
        summary = json.load(fh)
    assert summary["canonical_run_authorized"] is False, summary
    with DAG_VERDICT_JSON.open(encoding="utf-8") as fh:
        dag = json.load(fh)
    assert dag["canonical_run_authorized_anywhere"] is False, dag


def test_no_d002j_prereg_edit() -> None:
    import hashlib

    expected = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"  # pragma: allowlist secret
    actual = hashlib.sha256(D002J_PREREG.read_bytes()).hexdigest()
    assert actual == expected, f"D-002J prereg sha drift: {actual} != {expected}"
    assert D002J_PREREG.is_file(), "D-002J prereg must still exist"


# ---------------------------------------------------------------------------
# 23 merge markers + DAG self-consistency
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        IMPL_PY,
        MANIFEST_JSON,
        SUMMARY_JSON,
        PROTOCOL_MD,
        P4_CAPSULE_JSON,
        Path(__file__),
    ]
    hits: list[tuple[str, int]] = []
    for p in targets:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i))
    assert hits == [], f"unresolved merge markers: {hits}"
    # Cross-check: P4 capsule declares the correct parent and next.
    with P4_CAPSULE_JSON.open(encoding="utf-8") as fh:
        cap = json.load(fh)
    assert cap["parent_nodes"] == ["D002J-P3"], cap["parent_nodes"]
    assert cap["allowed_next_nodes"] == ["D002J-P5"], cap["allowed_next_nodes"]
