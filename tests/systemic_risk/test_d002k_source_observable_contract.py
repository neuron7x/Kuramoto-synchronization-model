# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P1 source & observable contract guard suite.

D-002K-P1 binds the six D-002K-P0-locked observable families to
P1B-audit-surviving funding-liquidity sources, the three D-002K crisis
windows (CW3/CW4/CW5), point-in-time release/vintage boundaries, and the
single P0-locked primary metric ``pre_post_standardized_mean_shift``.

This module is governance infra. It imports no physics, runs no
canonical sweep, fetches no data, and promotes no claim. It fails
closed if any future PR:

* binds an observable to a source that is NOT P1B-audit-surviving,
* binds an observable window outside {CW3, CW4, CW5},
* drops one of the six P0-locked observable families,
* loses the point-in-time vintage discipline,
* binds a contagion / balance-sheet / cross-asset source,
* mislabels a market-wide volatility control as a funding observable,
* mutates the D-002K-P0 prereg or any frozen D-002J artifact,
* promotes D-002K into a D-002J rescue or a systemic-risk claim.

D-002J stays REFUSED. D-002K is narrow by design, not relaxed.

All multi-line asserts use the msg-var idiom (``_amsg = ...`` extracted
above the ``assert``) so the module renders byte-identically under both
black and ruff-format (mirrors
``tests/governance/test_verdict_dag_integrity.py``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Anchors / constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

CONTRACT_PATH: Path = REPO_ROOT / "artifacts/d002k/observables/source_observable_contract_v1.json"
SUMMARY_PATH: Path = REPO_ROOT / "artifacts/d002k/observables/source_observable_summary_v1.json"
DOC_PATH: Path = REPO_ROOT / "docs/research/D002K_SOURCE_OBSERVABLE_CONTRACT.md"
P1_VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002k_p1_verdict_v1.json"
DAG_VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002j_verdict_dag_v1.json"
PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"
D002J_PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
P1B_REGISTRY_PATH: Path = REPO_ROOT / "artifacts/d002j/data_registry/source_registry_v1.json"
P1B_AUDIT_PATH: Path = REPO_ROOT / "artifacts/d002j/data_registry/source_provenance_audit_v1.json"

# Frozen byte-exact anchors (must not drift).
D002K_PREREG_SHA: str = "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"
D002J_PREREG_SHA: str = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"
P1B_REGISTRY_SHA: str = "f1899b7a882b4b3efbebb54e3dc942c079839f77f981273e2dd09757973b14ec"
P1B_AUDIT_SHA: str = "1e6f89299315bdc85d7929aa0883b44eee24af4474e33d4a2db95da446f7786c"

# The six P0-locked observable families.
P0_OBSERVABLE_FAMILIES: frozenset[str] = frozenset(
    {
        "level_shift",
        "spread_widening",
        "volatility_burst",
        "recovery_time",
        "transition_steepness",
        "stress_persistence",
    }
)

# The three D-002K-P0-locked crisis windows.
D002K_WINDOWS: frozenset[str] = frozenset(
    {
        "CW3_US_REPO_SPIKE_2019",
        "CW4_COVID_DASH_FOR_CASH_2020",
        "CW5_UK_GILT_LDI_2022",
    }
)

# Out-of-D-002K-scope windows that must NOT appear.
OUT_OF_SCOPE_WINDOWS: frozenset[str] = frozenset(
    {
        "CW1_GFC_2007_2009",
        "CW2_EUROZONE_2011_2012",
        "CW6_REGIONAL_BANKING_2023",
    }
)

P0_PRIMARY_METRIC: str = "pre_post_standardized_mean_shift"

# Source ids whose source_class is contagion / balance-sheet /
# cross-asset / interbank-network. D-002K must NEVER bind any of these.
FORBIDDEN_SOURCE_IDS: frozenset[str] = frozenset(
    {
        "BIS_CBS",
        "FDIC_CALL_REPORTS",
        "ECB_CBD",
        "FED_Y9C",
        "BIS_QR_NETWORK",
        "OFR_WP_NETWORK",
        "LIT_INTERBANK_CONTAGION",
        "LIT_NETWORK_RECON",
        "FDIC_SVB_POSTMORTEM",
    }
)

# VIX-class sources are controls, never funding-liquidity observables.
VIX_CLASS_SOURCE_IDS: frozenset[str] = frozenset({"CBOE_VIX"})

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    msg = f"{path} must be a JSON object; got {type(data).__name__}"
    assert isinstance(data, dict), msg
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observables() -> list[dict[str, Any]]:
    contract = _load_json(CONTRACT_PATH)
    obs = contract["observables"]
    assert isinstance(obs, list), "contract.observables must be a list"
    assert obs, "contract.observables must not be empty"
    return obs


def _p1b_surviving_source_ids() -> set[str]:
    registry = _load_json(P1B_REGISTRY_PATH)
    audit = _load_json(P1B_AUDIT_PATH)
    status = {x["source_id"]: x["audit_status"] for x in audit["sources"]}
    return {
        s["source_id"]
        for s in registry["sources"]
        if status.get(s["source_id"]) in ("VERIFIED", "PARTIAL")
    }


# ---------------------------------------------------------------------------
# 1. Existence + schema
# ---------------------------------------------------------------------------


def test_contract_exists() -> None:
    msg_file = f"D-002K-P1 contract missing: {CONTRACT_PATH}"
    assert CONTRACT_PATH.is_file(), msg_file
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert text.strip(), "contract must not be empty"


def test_summary_exists() -> None:
    msg_file = f"D-002K-P1 summary missing: {SUMMARY_PATH}"
    assert SUMMARY_PATH.is_file(), msg_file
    assert DOC_PATH.is_file(), f"design doc missing: {DOC_PATH}"


def test_contract_schema_version() -> None:
    contract = _load_json(CONTRACT_PATH)
    sv = contract["schema_version"]
    _amsg = f"contract schema_version must be D002K-SOURCE-OBSERVABLE-CONTRACT-v1; got {sv!r}"
    assert sv == "D002K-SOURCE-OBSERVABLE-CONTRACT-v1", _amsg
    summary = _load_json(SUMMARY_PATH)
    sv2 = summary["schema_version"]
    _amsg2 = f"summary schema_version must be D002K-SOURCE-OBSERVABLE-SUMMARY-v1; got {sv2!r}"
    assert sv2 == "D002K-SOURCE-OBSERVABLE-SUMMARY-v1", _amsg2


# ---------------------------------------------------------------------------
# 2. Phase-coupling K-P1 -> K-P0 (prereg byte-exact)
# ---------------------------------------------------------------------------


def test_parent_prereg_sha_pinned() -> None:
    contract = _load_json(CONTRACT_PATH)
    pinned = contract["parent_prereg_sha256"]
    actual = _sha256(PREREG_PATH)
    _amsg = (
        f"contract.parent_prereg_sha256 {pinned!r} must match the frozen "
        f"D-002K-P0 prereg sha {D002K_PREREG_SHA!r}"
    )
    assert pinned == D002K_PREREG_SHA, _amsg
    _amsg2 = (
        f"on-disk D-002K prereg sha {actual!r} drifted from frozen anchor "
        f"{D002K_PREREG_SHA!r} (K-P0 prereg must be byte-exact)"
    )
    assert actual == D002K_PREREG_SHA, _amsg2


# ---------------------------------------------------------------------------
# 3. Every P0 observable family covered
# ---------------------------------------------------------------------------


def test_every_observable_family_from_p0_covered() -> None:
    families = {o["observable_family"] for o in _observables()}
    missing = sorted(P0_OBSERVABLE_FAMILIES - families)
    _amsg = f"every P0-locked family must be covered; missing={missing}"
    assert not missing, _amsg
    extra = sorted(families - P0_OBSERVABLE_FAMILIES)
    _amsg2 = f"no observable family outside the 6 P0-locked families; extra={extra}"
    assert not extra, _amsg2


def test_min_six_observables() -> None:
    obs = _observables()
    _amsg = f"contract must declare >= 6 observables; got {len(obs)}"
    assert len(obs) >= 6, _amsg
    contract = _load_json(CONTRACT_PATH)
    _amsg2 = (
        f"contract.total_observables {contract['total_observables']} must "
        f"equal len(observables) {len(obs)}"
    )
    assert contract["total_observables"] == len(obs), _amsg2


# ---------------------------------------------------------------------------
# 4. Phase-coupling K-P1 -> J-P1B (sources)
# ---------------------------------------------------------------------------


def test_every_observable_source_in_p1b_surviving() -> None:
    surviving = _p1b_surviving_source_ids()
    assert surviving, "P1B-surviving set must be non-empty"
    for o in _observables():
        sid = o["source_id"]
        _amsg = (
            f"observable {o['observable_id']!r} source {sid!r} must be a "
            f"P1B-audit-surviving source (VERIFIED|PARTIAL)"
        )
        assert sid in surviving, _amsg


def test_no_observable_source_downgraded_or_rejected() -> None:
    audit = _load_json(P1B_AUDIT_PATH)
    status = {x["source_id"]: x["audit_status"] for x in audit["sources"]}
    for o in _observables():
        sid = o["source_id"]
        st = status.get(sid)
        _amsg = (
            f"observable {o['observable_id']!r} source {sid!r} audit_status "
            f"is {st!r}; only VERIFIED|PARTIAL may be bound"
        )
        assert st in ("VERIFIED", "PARTIAL"), _amsg
        declared = o["source_audit_status"]
        _amsg2 = (
            f"observable {o['observable_id']!r} declared source_audit_status "
            f"{declared!r} must match the P1B audit {st!r}"
        )
        assert declared == st, _amsg2


# ---------------------------------------------------------------------------
# 5. Phase-coupling K-P1 -> K-P0 (windows)
# ---------------------------------------------------------------------------


def test_every_observable_window_in_cw3_cw4_cw5() -> None:
    for o in _observables():
        windows = set(o["crisis_windows"])
        assert windows, f"observable {o['observable_id']!r} must declare >=1 window"
        bad = sorted(windows - D002K_WINDOWS)
        _amsg = (
            f"observable {o['observable_id']!r} windows {bad} not in the "
            f"D-002K-P0-locked {{CW3,CW4,CW5}} set"
        )
        assert not bad, _amsg


def test_no_observable_window_outside_d002k_scope() -> None:
    for o in _observables():
        windows = set(o["crisis_windows"])
        leaked = sorted(windows & OUT_OF_SCOPE_WINDOWS)
        _amsg = (
            f"observable {o['observable_id']!r} leaks out-of-scope windows "
            f"{leaked} (CW1/CW2/CW6 are NOT in D-002K)"
        )
        assert not leaked, _amsg


# ---------------------------------------------------------------------------
# 6. Point-in-time vintage discipline (executable)
# ---------------------------------------------------------------------------


def test_at_least_one_vintage_required_observable() -> None:
    vintaged = [o for o in _observables() if o["release_boundary"]["vintage_required"] is True]
    _amsg = (
        f"point-in-time discipline requires >=1 vintage_required observable; got {len(vintaged)}"
    )
    assert len(vintaged) >= 1, _amsg
    summary = _load_json(SUMMARY_PATH)
    _amsg2 = (
        f"summary.vintage_required_count {summary['vintage_required_count']} "
        f"must equal contract count {len(vintaged)}"
    )
    assert summary["vintage_required_count"] == len(vintaged), _amsg2


def test_vintage_required_observables_have_vintage_field() -> None:
    for o in _observables():
        rb = o["release_boundary"]
        if rb["vintage_required"] is True:
            _amsg = (
                f"observable {o['observable_id']!r} is vintage_required but "
                f"vintage_field is {rb['vintage_field']!r}"
            )
            assert rb["vintage_field"] == "release_date", _amsg
        else:
            _amsg2 = (
                f"observable {o['observable_id']!r} not vintage_required must "
                f"have vintage_field null; got {rb['vintage_field']!r}"
            )
            assert rb["vintage_field"] is None, _amsg2


def test_lookahead_invariants_present_each_observable() -> None:
    required = {
        "observation_date <= decision_date",
        "release_date <= decision_date",
    }
    for o in _observables():
        inv = set(o["release_boundary"]["lookahead_invariants"])
        missing = sorted(required - inv)
        _amsg = (
            f"observable {o['observable_id']!r} missing look-ahead invariants "
            f"{missing} (D-002I/D-002J look-ahead lesson)"
        )
        assert not missing, _amsg


# ---------------------------------------------------------------------------
# 7. Primary-metric mapping == P0 lock
# ---------------------------------------------------------------------------


def test_primary_metric_mapping_matches_p0_lock() -> None:
    contract = _load_json(CONTRACT_PATH)
    _amsg = (
        f"contract.primary_metric {contract['primary_metric']!r} must equal "
        f"the P0 lock {P0_PRIMARY_METRIC!r}"
    )
    assert contract["primary_metric"] == P0_PRIMARY_METRIC, _amsg
    for o in _observables():
        pm = o["primary_metric_mapping"]
        _amsg2 = (
            f"observable {o['observable_id']!r} primary_metric_mapping {pm!r} "
            f"must equal the P0 lock {P0_PRIMARY_METRIC!r}"
        )
        assert pm == P0_PRIMARY_METRIC, _amsg2


# ---------------------------------------------------------------------------
# 8. Control / observable separation
# ---------------------------------------------------------------------------


def test_vix_class_marked_control_not_observable() -> None:
    seen_vix = False
    for o in _observables():
        if o["source_id"] in VIX_CLASS_SOURCE_IDS:
            seen_vix = True
            _amsg = (
                f"observable {o['observable_id']!r} (VIX-class source "
                f"{o['source_id']!r}) must be role=control_covariate, "
                f"got {o['role']!r}"
            )
            assert o["role"] == "control_covariate", _amsg
        else:
            _amsg2 = (
                f"observable {o['observable_id']!r} role {o['role']!r} must be "
                f"funding_liquidity_observable or control_covariate"
            )
            assert o["role"] in (
                "funding_liquidity_observable",
                "control_covariate",
            ), _amsg2
    assert seen_vix, "expected a VIX-class control covariate present in the contract"


# ---------------------------------------------------------------------------
# 9. Funding-liquidity narrowness enforced
# ---------------------------------------------------------------------------


def test_no_contagion_or_balance_sheet_source_bound() -> None:
    bound = {o["source_id"] for o in _observables()}
    leaked = sorted(bound & FORBIDDEN_SOURCE_IDS)
    _amsg = (
        f"D-002K is funding-liquidity ONLY; contagion/balance-sheet/"
        f"cross-asset sources bound: {leaked}"
    )
    assert not leaked, _amsg
    summary = _load_json(SUMMARY_PATH)
    cnt = summary["contagion_or_balance_sheet_sources_bound"]
    _amsg2 = f"summary must report 0 contagion/balance-sheet sources; got {cnt}"
    assert cnt == 0, _amsg2


# ---------------------------------------------------------------------------
# 10. Summary counts match contract
# ---------------------------------------------------------------------------


def test_summary_counts_match_contract() -> None:
    obs = _observables()
    summary = _load_json(SUMMARY_PATH)
    by_family: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for o in obs:
        by_family[o["observable_family"]] = by_family.get(o["observable_family"], 0) + 1
        by_source[o["source_id"]] = by_source.get(o["source_id"], 0) + 1
    _amsg = (
        f"summary.counts_by_observable_family {summary['counts_by_observable_family']} "
        f"!= recomputed {by_family}"
    )
    assert summary["counts_by_observable_family"] == by_family, _amsg
    _amsg2 = (
        f"summary.counts_by_source_id {summary['counts_by_source_id']} != recomputed {by_source}"
    )
    assert summary["counts_by_source_id"] == by_source, _amsg2
    _amsg3 = (
        f"summary.total_observables {summary['total_observables']} != len(observables) {len(obs)}"
    )
    assert summary["total_observables"] == len(obs), _amsg3


# ---------------------------------------------------------------------------
# 11. No forbidden claims
# ---------------------------------------------------------------------------


def test_no_systemic_risk_prediction_claim() -> None:
    blob = (
        CONTRACT_PATH.read_text(encoding="utf-8")
        + SUMMARY_PATH.read_text(encoding="utf-8")
        + P1_VERDICT_PATH.read_text(encoding="utf-8")
    ).lower()
    for banned in ("predicts systemic", "systemic-risk prediction", "predict crises"):
        _amsg = f"D-002K-P1 must not assert a systemic-risk prediction; found {banned!r}"
        assert banned not in blob, _amsg
    for o in _observables():
        joined = " ".join(o["forbidden_use"]).lower()
        _amsg2 = (
            f"observable {o['observable_id']!r} must forbid systemic-risk "
            f"predictor use in forbidden_use"
        )
        assert "not a systemic-risk predictor" in joined, _amsg2


def test_no_bank_level_validation_claim() -> None:
    for o in _observables():
        joined = " ".join(o["forbidden_use"]).lower()
        _amsg = (
            f"observable {o['observable_id']!r} must forbid bank-level validation in forbidden_use"
        )
        assert "not bank-level validation" in joined, _amsg
    blob = CONTRACT_PATH.read_text(encoding="utf-8").lower()
    _amsg2 = "contract must not assert bank-level validation"
    assert "is bank-level validated" not in blob, _amsg2


# ---------------------------------------------------------------------------
# 12. Frozen artifacts
# ---------------------------------------------------------------------------


def test_no_d002k_prereg_edit() -> None:
    actual = _sha256(PREREG_PATH)
    _amsg = (
        f"D-002K-P0 prereg sha {actual!r} drifted from frozen anchor "
        f"{D002K_PREREG_SHA!r}; K-P0 prereg is byte-exact"
    )
    assert actual == D002K_PREREG_SHA, _amsg


def test_no_d002j_artifacts_modified() -> None:
    j_prereg = _sha256(D002J_PREREG_PATH)
    _amsg = (
        f"D-002J prereg sha {j_prereg!r} drifted from frozen anchor "
        f"{D002J_PREREG_SHA!r}; D-002J is frozen"
    )
    assert j_prereg == D002J_PREREG_SHA, _amsg
    reg = _sha256(P1B_REGISTRY_PATH)
    _amsg2 = (
        f"D-002J P1B source registry sha {reg!r} drifted from frozen anchor "
        f"{P1B_REGISTRY_SHA!r}; artifacts/d002j/** is frozen"
    )
    assert reg == P1B_REGISTRY_SHA, _amsg2
    aud = _sha256(P1B_AUDIT_PATH)
    _amsg3 = (
        f"D-002J P1B audit sha {aud!r} drifted from frozen anchor "
        f"{P1B_AUDIT_SHA!r}; artifacts/d002j/** is frozen"
    )
    assert aud == P1B_AUDIT_SHA, _amsg3


# ---------------------------------------------------------------------------
# 13. No canonical run / verdict structure
# ---------------------------------------------------------------------------


def test_no_canonical_run_authorized() -> None:
    verdict = _load_json(P1_VERDICT_PATH)
    _amsg = f"P1 verdict node_id must be D002K-P1; got {verdict['node_id']!r}"
    assert verdict["node_id"] == "D002K-P1", _amsg
    _amsg2 = (
        f"P1 verdict decision must be D002K_SOURCE_OBSERVABLE_CONTRACT_READY; "
        f"got {verdict['decision']!r}"
    )
    assert verdict["decision"] == "D002K_SOURCE_OBSERVABLE_CONTRACT_READY", _amsg2
    _amsg3 = f"P1 verdict parent_nodes must be ['D002K-P0']; got {verdict['parent_nodes']!r}"
    assert verdict["parent_nodes"] == ["D002K-P0"], _amsg3
    _amsg4 = (
        f"P1 verdict allowed_next_nodes must be ['D002K-P2']; got {verdict['allowed_next_nodes']!r}"
    )
    assert verdict["allowed_next_nodes"] == ["D002K-P2"], _amsg4
    dag = _load_json(DAG_VERDICT_PATH)
    _amsg5 = (
        f"DAG canonical_run_authorized_anywhere must stay false; "
        f"got {dag['canonical_run_authorized_anywhere']!r}"
    )
    assert dag["canonical_run_authorized_anywhere"] is False, _amsg5
    # Monotonic-retention invariant: D002J-P1A + D002J-P7 must STAY
    # rejected as later D-002K phases land. The list only ever grows
    # (e.g. D-002K-P4's honest POWER_GATE_REFUSED_UNDERPOWERED joins
    # it); it never drops a prior retained negative. Subset check, not
    # exact-list lock.
    _amsg6 = (
        f"DAG must retain D002J-P1A + D002J-P7 rejected; got {dag['rejected_nodes_retained']!r}"
    )
    assert {"D002J-P1A", "D002J-P7"}.issubset(set(dag["rejected_nodes_retained"])), _amsg6
    # The DAG advances monotonically as later D-002K phases land
    # (K-P2 -> 13 nodes, ...). K-P1 only requires that its own node is
    # retained and the DAG has not shrunk below the K-P1 snapshot.
    _amsg7 = f"DAG nodes_count must be >= 12 (K-P1 snapshot floor); got {dag['nodes_count']!r}"
    assert int(dag["nodes_count"]) >= 12, _amsg7
    _amsg8 = f"D002K-P1 must remain in topological_order; got {dag['topological_order']!r}"
    assert "D002K-P1" in dag["topological_order"], _amsg8


def test_no_unresolved_merge_markers() -> None:
    targets = [CONTRACT_PATH, SUMMARY_PATH, DOC_PATH, P1_VERDICT_PATH]
    for path in targets:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            _amsg = f"unresolved merge marker in {path} at line {lineno}: {line!r}"
            assert not _MARKER.match(line), _amsg
    assert len(targets) == 4, "expected exactly 4 D-002K-P1 text artifacts scanned"
