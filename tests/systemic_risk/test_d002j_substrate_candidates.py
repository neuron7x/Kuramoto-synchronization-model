# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P5 guard tests — financial-mechanistic substrate candidates v1.

Enforces the operator-locked admission criterion (EXACTLY 3 substrates;
>=1 contagion-class + >=1 funding/liquidity-class + >=1 market/info-class;
collective P2-window coverage >=4 of 6; no real interbank transaction
microdata), the phase-coupling invariants P5->{P1B,P2,P3,P4}, the
Brunetti e-MID cross-asset/interbank scope guard (executable), and
substrate determinism.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

from research.systemic_risk.substrates.d002j import (
    CrossExposureContagionProxySubstrate,
    FundingLiquidityRolloverSubstrate,
    VolatilityCreditSpreadRegimeSubstrate,
)
from research.systemic_risk.substrates.d002j.substrate_base import SubstrateInstance


class _SubstrateProto(Protocol):
    def simulate(self, seed: int, params: dict[str, float] | None = None) -> SubstrateInstance: ...


REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SUB_DIR: Path = REPO_ROOT / "artifacts" / "d002j" / "substrates"
MANIFEST_JSON: Path = SUB_DIR / "substrate_candidate_manifest_v1.json"
SUMMARY_JSON: Path = SUB_DIR / "substrate_summary_v1.json"
DESIGN_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_FINANCIAL_SUBSTRATE_DESIGN_SPACE.md"
P5_CAPSULE_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_p5_verdict_v1.json"
)
DAG_VERDICT_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_verdict_dag_v1.json"
)
P1B_AUDIT_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_provenance_audit_v1.json"
)
P2_REGISTRY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "crisis_windows" / "crisis_window_registry_v1.json"
)
P3_ADAPTER_JSON: Path = REPO_ROOT / "artifacts" / "d002j" / "ingestion" / "adapter_registry_v1.json"
P4_MANIFEST_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "positive_controls" / "positive_control_manifest_v1.json"
)
D002J_PREREG: Path = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")

_CONTAGION_CLASS = {"contagion"}
_FUNDING_CLASS = {"funding_liquidity"}
_MARKET_INFO_CLASS = {"market_information"}

_SUBSTRATE_CLASSES: dict[str, type[_SubstrateProto]] = {
    "funding_liquidity_rollover": FundingLiquidityRolloverSubstrate,
    "cross_exposure_contagion_proxy": CrossExposureContagionProxySubstrate,
    "volatility_credit_spread_regime": VolatilityCreditSpreadRegimeSubstrate,
}


def _load_json(path: Path) -> dict[str, Any]:
    import json

    with path.open(encoding="utf-8") as fh:
        return cast(dict[str, Any], json.load(fh))


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_JSON)


def _substrates() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], _manifest()["substrates"])


def _p1b_status_map() -> dict[str, str]:
    audit = _load_json(P1B_AUDIT_JSON)
    return {
        cast(str, s["source_id"]): cast(str, s.get("audit_status", s.get("status", "")))
        for s in cast(list[dict[str, Any]], audit["sources"])
    }


def _p2_window_ids() -> set[str]:
    reg = _load_json(P2_REGISTRY_JSON)
    return {cast(str, w["window_id"]) for w in cast(list[dict[str, Any]], reg["windows"])}


def _p3_adapter_ids() -> set[str]:
    reg = _load_json(P3_ADAPTER_JSON)
    return {cast(str, a["adapter_id"]) for a in cast(list[dict[str, Any]], reg["adapters"])}


def _p4_control_ids() -> set[str]:
    man = _load_json(P4_MANIFEST_JSON)
    fams = cast(list[dict[str, Any]], man.get("control_families", man.get("controls", [])))
    return {cast(str, c["control_family_id"]) for c in fams}


def _claim_strict_files() -> tuple[Path, ...]:
    """Files where forbidden phrases must NOT appear at all.

    The manifest JSON and the design markdown ARE the declaration
    surface (they negate the forbidden phrases inside forbidden /
    scope-guard blocks) and are EXCLUDED from the strict scan. The
    summary JSON is a pure decision artifact and may NOT carry any
    forbidden phrase — it is the single strict file.
    """
    return (SUMMARY_JSON,)


# ---------------------------------------------------------------------------
# 1-2 existence
# ---------------------------------------------------------------------------


def test_substrate_manifest_exists() -> None:
    assert MANIFEST_JSON.is_file(), f"missing manifest: {MANIFEST_JSON}"
    man = _manifest()
    assert man["schema_version"] == "D002J-SUBSTRATE-CANDIDATE-MANIFEST-v1", man["schema_version"]


def test_substrate_summary_exists() -> None:
    assert SUMMARY_JSON.is_file(), f"missing summary: {SUMMARY_JSON}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["schema_version"] == "D002J-SUBSTRATE-SUMMARY-v1", summ["schema_version"]
    assert summ["decision"] == "SUBSTRATE_CANDIDATES_READY", summ["decision"]


# ---------------------------------------------------------------------------
# 3 exactly three
# ---------------------------------------------------------------------------


def test_exactly_three_substrates_admitted() -> None:
    subs = _substrates()
    assert len(subs) == 3, f"operator-locked floor is EXACTLY 3; got {len(subs)}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["total_substrates"] == 3, summ["total_substrates"]


# ---------------------------------------------------------------------------
# 4-6 class coverage
# ---------------------------------------------------------------------------


def test_at_least_one_contagion_class_substrate() -> None:
    classes = [s["substrate_class"] for s in _substrates()]
    n = sum(1 for c in classes if c in _CONTAGION_CLASS)
    assert n >= 1, f">=1 contagion-class substrate required; classes={classes}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["class_coverage_check"]["contagion_class_present"] is True


def test_at_least_one_funding_liquidity_class_substrate() -> None:
    classes = [s["substrate_class"] for s in _substrates()]
    n = sum(1 for c in classes if c in _FUNDING_CLASS)
    assert n >= 1, f">=1 funding/liquidity-class substrate required; classes={classes}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["class_coverage_check"]["funding_liquidity_class_present"] is True


def test_at_least_one_market_or_information_class_substrate() -> None:
    classes = [s["substrate_class"] for s in _substrates()]
    n = sum(1 for c in classes if c in _MARKET_INFO_CLASS)
    assert n >= 1, f">=1 market/information-class substrate required; classes={classes}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["class_coverage_check"]["market_or_information_class_present"] is True


# ---------------------------------------------------------------------------
# 7-8 phase-coupling P5 -> P1B
# ---------------------------------------------------------------------------


def test_each_substrate_has_min_two_p1b_surviving_sources() -> None:
    status = _p1b_status_map()
    surviving = {sid for sid, st in status.items() if st in ("VERIFIED", "PARTIAL")}
    short: dict[str, list[str]] = {}
    for s in _substrates():
        sids = cast(list[str], s["source_ids"])
        ok = [x for x in sids if x in surviving]
        if len(ok) < 2:
            short[s["substrate_id"]] = ok
    assert not short, f"substrate(s) with <2 P1B-surviving sources: {short}"
    for s in _substrates():
        assert len(set(s["source_ids"])) >= 2, s["substrate_id"]


def test_each_substrate_source_is_p1b_verified_or_partial() -> None:
    status = _p1b_status_map()
    bad: dict[str, dict[str, str]] = {}
    for s in _substrates():
        offenders = {
            sid: status.get(sid, "MISSING")
            for sid in s["source_ids"]
            if status.get(sid) not in ("VERIFIED", "PARTIAL")
        }
        if offenders:
            bad[s["substrate_id"]] = offenders
    assert not bad, f"non-P1B-surviving sources bound by substrate(s): {bad}"
    # Distinct second case: no DOWNGRADED/REJECTED status anywhere bound.
    for s in _substrates():
        for sid in s["source_ids"]:
            assert status.get(sid) not in ("DOWNGRADED", "REJECTED"), (s["substrate_id"], sid)


# ---------------------------------------------------------------------------
# 9-10 phase-coupling P5 -> P2
# ---------------------------------------------------------------------------


def test_each_substrate_has_min_one_p2_crisis_window() -> None:
    bad = [s["substrate_id"] for s in _substrates() if len(s.get("crisis_windows", [])) < 1]
    assert not bad, f"substrate(s) with no P2 crisis window: {bad}"
    for s in _substrates():
        assert len(s["crisis_windows"]) >= 1, s["substrate_id"]


def test_each_substrate_window_id_exists_in_p2_registry() -> None:
    valid = _p2_window_ids()
    bad: dict[str, list[str]] = {}
    for s in _substrates():
        miss = [w for w in s["crisis_windows"] if w not in valid]
        if miss:
            bad[s["substrate_id"]] = miss
    assert not bad, f"substrate window_ids not in P2 registry: {bad}; valid={sorted(valid)}"
    for s in _substrates():
        assert set(s["crisis_windows"]) <= valid, s["substrate_id"]


# ---------------------------------------------------------------------------
# 11-12 phase-coupling P5 -> P3
# ---------------------------------------------------------------------------


def test_each_substrate_has_min_one_p3_adapter_binding() -> None:
    bad = [s["substrate_id"] for s in _substrates() if len(s.get("p3_adapter_ids", [])) < 1]
    assert not bad, f"substrate(s) with no P3 adapter binding: {bad}"
    for s in _substrates():
        assert len(s["p3_adapter_ids"]) >= 1, s["substrate_id"]


def test_each_substrate_adapter_id_exists_in_p3_manifest() -> None:
    valid = _p3_adapter_ids()
    bad: dict[str, list[str]] = {}
    for s in _substrates():
        miss = [a for a in s["p3_adapter_ids"] if a not in valid]
        if miss:
            bad[s["substrate_id"]] = miss
    assert not bad, f"substrate adapter_ids not in P3 manifest: {bad}"
    for s in _substrates():
        assert set(s["p3_adapter_ids"]) <= valid, s["substrate_id"]


# ---------------------------------------------------------------------------
# 13-14 phase-coupling P5 -> P4
# ---------------------------------------------------------------------------


def test_each_substrate_has_min_one_p4_positive_control() -> None:
    bad = [
        s["substrate_id"] for s in _substrates() if len(s.get("positive_control_analogues", [])) < 1
    ]
    assert not bad, f"substrate(s) with no P4 positive-control analogue: {bad}"
    for s in _substrates():
        assert len(s["positive_control_analogues"]) >= 1, s["substrate_id"]


def test_each_substrate_pc_analogue_exists_in_p4_manifest() -> None:
    valid = _p4_control_ids()
    bad: dict[str, list[str]] = {}
    for s in _substrates():
        miss = [c for c in s["positive_control_analogues"] if c not in valid]
        if miss:
            bad[s["substrate_id"]] = miss
    assert not bad, f"substrate PC analogues not in P4 manifest: {bad}; valid={sorted(valid)}"
    for s in _substrates():
        assert set(s["positive_control_analogues"]) <= valid, s["substrate_id"]


# ---------------------------------------------------------------------------
# 15 forward-decl to P6
# ---------------------------------------------------------------------------


def test_each_substrate_declares_min_two_required_null_families() -> None:
    bad: dict[str, list[str]] = {}
    for s in _substrates():
        nf = cast(list[str], s.get("required_null_families", []))
        if len(set(nf)) < 2:
            bad[s["substrate_id"]] = nf
    assert not bad, f"substrate(s) with <2 forward-declared null families: {bad}"
    for s in _substrates():
        assert len(set(s["required_null_families"])) >= 2, s["substrate_id"]


# ---------------------------------------------------------------------------
# 16 combined window coverage
# ---------------------------------------------------------------------------


def test_combined_window_coverage_at_least_four_of_six() -> None:
    covered: set[str] = set()
    for s in _substrates():
        covered.update(s["crisis_windows"])
    assert len(covered) >= 4, f"combined window coverage {len(covered)}/6 < 4; covered={covered}"
    summ = _load_json(SUMMARY_JSON)
    assert summ["windows_covered_count"] == len(covered), (summ["windows_covered_count"], covered)
    assert summ["window_coverage_floor_met"] is True


# ---------------------------------------------------------------------------
# 17 determinism (simulate twice, numpy-equal)
# ---------------------------------------------------------------------------


def test_each_substrate_simulate_is_deterministic() -> None:
    seeds = (42, 7, 2026)
    for sid, cls in _SUBSTRATE_CLASSES.items():
        sub = cls()
        for seed in seeds:
            a = sub.simulate(seed)
            b = sub.simulate(seed)
            np.testing.assert_array_equal(
                a.state_trajectory, b.state_trajectory, err_msg=f"{sid} state non-det @{seed}"
            )
            assert set(a.observable_outputs) == set(b.observable_outputs), sid
            for k in a.observable_outputs:
                np.testing.assert_array_equal(
                    a.observable_outputs[k],
                    b.observable_outputs[k],
                    err_msg=f"{sid}:{k} non-deterministic @ seed {seed}",
                )


# ---------------------------------------------------------------------------
# 18 observable keys match manifest
# ---------------------------------------------------------------------------


def test_each_substrate_observable_outputs_match_manifest_keys() -> None:
    by_id = {s["substrate_id"]: s for s in _substrates()}
    for sid, cls in _SUBSTRATE_CLASSES.items():
        assert sid in by_id, f"{sid} missing from manifest"
        declared = set(by_id[sid]["observable_outputs"])
        inst = cls().simulate(123)
        produced = set(inst.observable_outputs)
        assert produced == declared, f"{sid}: produced {produced} != manifest {declared}"
        assert len(declared) >= 2, f"{sid} must declare >=2 observable outputs"


# ---------------------------------------------------------------------------
# 19 no real interbank transaction data
# ---------------------------------------------------------------------------


def test_no_substrate_requires_real_interbank_transaction_data() -> None:
    for s in _substrates():
        assert s.get("requires_real_interbank_transaction_data") is False, s["substrate_id"]
    # Distinct second case: each substrate instance metadata also flags False.
    for sid, cls in _SUBSTRATE_CLASSES.items():
        meta = cls().simulate(1).metadata
        assert meta.get("requires_real_interbank_transaction_data") is False, sid
    summ = _load_json(SUMMARY_JSON)
    assert summ["interbank_transaction_microdata_required_by_any_substrate"] is False


# ---------------------------------------------------------------------------
# 20 Brunetti scope guard executable
# ---------------------------------------------------------------------------


def test_cross_asset_interbank_distinction_documented() -> None:
    # Strict scan: no affirmative cross-asset...interbank...(proves|validates|
    # confirms) in the strict (decision-only) file set.
    pattern = re.compile(
        r"cross[-\s]asset[\s\S]{0,200}interbank[\s\S]{0,200}(validate[sd]?|prove[sd]?|confirm[sd]?)"
    )
    leaks: list[tuple[str, str]] = []
    for path in _claim_strict_files():
        text = path.read_text(encoding="utf-8").lower()
        for m in pattern.finditer(text):
            leaks.append((str(path), text[max(0, m.start() - 60) : m.end() + 60]))
    assert not leaks, f"cross-asset/interbank overclaim leak(s) in strict file(s): {leaks[:2]}"
    # Distinct second case: manifest declares the scope guard + Brunetti
    # is named in the design doc.
    man = _manifest()
    guard = cast(dict[str, Any], man["cross_asset_interbank_scope_guard"])
    assert guard["interbank_transaction_microdata_forbidden"] is True, guard
    design = DESIGN_MD.read_text(encoding="utf-8").lower()
    assert "brunetti" in design, "design doc must name the Brunetti e-MID scope guard"
    assert "e-mid" in design, "design doc must reference e-MID"


# ---------------------------------------------------------------------------
# 21 no real-bank validation claim
# ---------------------------------------------------------------------------


def test_no_real_bank_validation_claim() -> None:
    bad_pat = re.compile(r"(validate[sd]?|prove[sd]?|confirm[sd]?)\s+real[-\s]bank")
    for path in _claim_strict_files():
        text = path.read_text(encoding="utf-8").lower()
        assert not bad_pat.search(text), f"real-bank-validation leak in {path}"
    # Distinct second case: every substrate forbids it explicitly.
    for s in _substrates():
        joined = " ".join(s["forbidden_claims"]).lower()
        assert "real-bank systemic risk" in joined, s["substrate_id"]


# ---------------------------------------------------------------------------
# 22 no canonical run authorized
# ---------------------------------------------------------------------------


def test_no_canonical_run_authorized() -> None:
    summ = _load_json(SUMMARY_JSON)
    assert summ["canonical_run_authorized"] is False, summ
    dag = _load_json(DAG_VERDICT_JSON)
    assert dag["canonical_run_authorized_anywhere"] is False, dag


# ---------------------------------------------------------------------------
# 23 no D-002J prereg edit
# ---------------------------------------------------------------------------


def test_no_d002j_prereg_edit() -> None:
    expected = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"  # pragma: allowlist secret
    actual = hashlib.sha256(D002J_PREREG.read_bytes()).hexdigest()
    assert actual == expected, f"D-002J prereg sha drift: {actual} != {expected}"
    assert D002J_PREREG.is_file(), "D-002J prereg must still exist"


# ---------------------------------------------------------------------------
# 24 no unresolved merge markers
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        MANIFEST_JSON,
        SUMMARY_JSON,
        DESIGN_MD,
        P5_CAPSULE_JSON,
        REPO_ROOT / "research" / "systemic_risk" / "substrates" / "d002j" / "__init__.py",
        REPO_ROOT
        / "research"
        / "systemic_risk"
        / "substrates"
        / "d002j"
        / "funding_liquidity_rollover.py",
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
    # Cross-check: P5 capsule declares correct parent and next.
    cap = _load_json(P5_CAPSULE_JSON)
    assert cap["parent_nodes"] == ["D002J-P4"], cap["parent_nodes"]
    assert cap["allowed_next_nodes"] == ["D002J-P6"], cap["allowed_next_nodes"]
