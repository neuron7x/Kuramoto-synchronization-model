# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P2 matched-placebo-window guard suite.

D-002K-P2 produces a deterministic, seed-locked registry of matched
NON-crisis placebo windows: ``n_placebo_per_crisis`` (from the K-P0
``matched_placebo_policy`` lock) matched placebos for each of the three
D-002K crisis windows (CW3 / CW4 / CW5), whose dates are pulled
read-only from the FROZEN D-002J P2 crisis-window registry.

This module is governance / research infra. It imports no physics, runs
no canonical sweep, fetches no data, and promotes no claim. It fails
closed if any future PR:

* lets a placebo intersect ANY of the six D-002J registered windows,
* breaks the exact trading-day calendar-length match,
* breaks determinism (same seed -> different placebo set),
* drifts the K-P0 ``n_placebo_per_crisis`` / ``match_on`` lock,
* introduces a hand-picked / manual-override placebo,
* mutates a frozen D-002J / K-P0 / K-P1 artifact,
* promotes D-002K into a D-002J rescue or a systemic-risk claim.

D-002J stays REFUSED. The crisis-vs-placebo contrast is PREDEFINED by a
deterministic algorithm, never hand-selected.

All multi-line asserts use the msg-var idiom (``_amsg = ...`` extracted
above the ``assert``) so the module renders byte-identically under both
black 26.3.1 and ruff-format 0.14.0.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from research.systemic_risk.d002k_placebo_selection import (
    LOCKED_SELECTION_SEED,
    load_crisis_window,
    select_matched_placebos,
)

# ---------------------------------------------------------------------------
# Anchors / constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

REGISTRY_PATH: Path = REPO_ROOT / "artifacts/d002k/placebo/matched_placebo_registry_v1.json"
SUMMARY_PATH: Path = REPO_ROOT / "artifacts/d002k/placebo/matched_placebo_summary_v1.json"
DOC_PATH: Path = REPO_ROOT / "docs/research/D002K_MATCHED_PLACEBO_PROTOCOL.md"
P2_VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002k_p2_verdict_v1.json"
DAG_VERDICT_PATH: Path = REPO_ROOT / "artifacts/governance/verdicts/d002j_verdict_dag_v1.json"
PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"
D002J_PREREG_PATH: Path = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
CRISIS_REGISTRY_PATH: Path = (
    REPO_ROOT / "artifacts/d002j/crisis_windows/crisis_window_registry_v1.json"
)
SELECTOR_PATH: Path = REPO_ROOT / "research/systemic_risk/d002k_placebo_selection.py"

# Frozen byte-exact anchors (must not drift).
D002K_PREREG_SHA: str = "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"
D002J_PREREG_SHA: str = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"
CRISIS_REGISTRY_SHA: str = "41f281d9e97fbf49725f0eb1a1bb7b45865c14cdc5c525ea96231ef0aa651e8f"

CW3: str = "CW3_US_REPO_SPIKE_2019"
CW4: str = "CW4_COVID_DASH_FOR_CASH_2020"
CW5: str = "CW5_UK_GILT_LDI_2022"
PRIMARY: tuple[str, str, str] = (CW3, CW4, CW5)

ALL_REGISTERED: tuple[str, ...] = (
    "CW1_GFC_2007_2009",
    "CW2_EUROZONE_2011_2012",
    CW3,
    CW4,
    CW5,
    "CW6_REGIONAL_BANKING_2023",
)

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    assert isinstance(payload, dict), f"{path} must hold a JSON object"
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry() -> dict[str, Any]:
    return _load_json(REGISTRY_PATH)


def _summary() -> dict[str, Any]:
    return _load_json(SUMMARY_PATH)


def _k_p0_policy() -> dict[str, Any]:
    with PREREG_PATH.open(encoding="utf-8") as fh:
        prereg = yaml.safe_load(fh)
    pol = prereg["matched_placebo_policy"]
    assert isinstance(pol, dict), "matched_placebo_policy must be a mapping"
    return pol


def _registered_intervals() -> list[tuple[str, dt.date, dt.date]]:
    reg = _load_json(CRISIS_REGISTRY_PATH)
    out: list[tuple[str, dt.date, dt.date]] = []
    for win in reg["windows"]:
        out.append(
            (
                win["window_id"],
                dt.date.fromisoformat(win["pre_event_buffer"]),
                dt.date.fromisoformat(win["post_event_buffer"]),
            )
        )
    return out


def _interval_overlap(a_start: dt.date, a_end: dt.date, b_start: dt.date, b_end: dt.date) -> bool:
    return a_start <= b_end and b_start <= a_end


# ---------------------------------------------------------------------------
# 1-2. Artifacts exist
# ---------------------------------------------------------------------------


def test_placebo_registry_exists() -> None:
    assert REGISTRY_PATH.is_file(), f"missing placebo registry {REGISTRY_PATH}"
    reg = _registry()
    assert reg["placebos"], "registry must carry a non-empty placebos list"


def test_placebo_summary_exists() -> None:
    assert SUMMARY_PATH.is_file(), f"missing placebo summary {SUMMARY_PATH}"
    summ = _summary()
    assert "counts" in summ, "summary must carry a counts block"


# ---------------------------------------------------------------------------
# 3. Schema version
# ---------------------------------------------------------------------------


def test_registry_schema_version() -> None:
    reg = _registry()
    _amsg = f"registry schema must be D002K-MATCHED-PLACEBO-REGISTRY-v1; got {reg.get('schema_version')!r}"
    assert reg["schema_version"] == "D002K-MATCHED-PLACEBO-REGISTRY-v1", _amsg
    summ = _summary()
    _amsg2 = f"summary schema must be D002K-MATCHED-PLACEBO-SUMMARY-v1; got {summ.get('schema_version')!r}"
    assert summ["schema_version"] == "D002K-MATCHED-PLACEBO-SUMMARY-v1", _amsg2


# ---------------------------------------------------------------------------
# 4. Parent K-P0 prereg sha pinned (K-P2 -> K-P0 coupling)
# ---------------------------------------------------------------------------


def test_parent_prereg_sha_pinned() -> None:
    actual = _sha256(PREREG_PATH)
    _amsg = f"K-P0 prereg sha drift: expected {D002K_PREREG_SHA}, got {actual}"
    assert actual == D002K_PREREG_SHA, _amsg
    reg = _registry()
    _amsg2 = "registry must pin parent_prereg_sha256 to the frozen K-P0 prereg sha"
    assert reg["parent_prereg_sha256"] == D002K_PREREG_SHA, _amsg2


# ---------------------------------------------------------------------------
# 5. Parent crisis-registry sha pinned (K-P2 -> J-P2 frozen-ref coupling)
# ---------------------------------------------------------------------------


def test_parent_crisis_registry_sha_pinned() -> None:
    actual = _sha256(CRISIS_REGISTRY_PATH)
    _amsg = f"D-002J P2 crisis registry sha drift: expected {CRISIS_REGISTRY_SHA}, got {actual}"
    assert actual == CRISIS_REGISTRY_SHA, _amsg
    reg = _registry()
    _amsg2 = "registry must pin parent_crisis_registry_sha256 to the frozen D-002J P2 registry"
    assert reg["parent_crisis_registry_sha256"] == CRISIS_REGISTRY_SHA, _amsg2


# ---------------------------------------------------------------------------
# 6. Three crisis windows covered (CW3/CW4/CW5)
# ---------------------------------------------------------------------------


def test_three_crisis_windows_covered_cw3_cw4_cw5() -> None:
    summ = _summary()
    per = summ["counts"]["per_crisis"]
    _amsg = f"summary per_crisis must cover exactly {set(PRIMARY)}; got {set(per)}"
    assert set(per) == set(PRIMARY), _amsg
    reg = _registry()
    parents = {p["parent_crisis_window_id"] for p in reg["placebos"]}
    _amsg2 = f"registry parents must be exactly {set(PRIMARY)}; got {parents}"
    assert parents == set(PRIMARY), _amsg2


# ---------------------------------------------------------------------------
# 7. n_placebo_per_crisis == K-P0 lock (policy conformance)
# ---------------------------------------------------------------------------


def test_n_placebo_per_crisis_matches_k_p0_lock() -> None:
    pol = _k_p0_policy()
    locked_n = int(pol["n_placebo_per_crisis"])
    reg = _registry()
    _amsg = f"registry n_placebo_per_crisis must equal K-P0 lock {locked_n}; got {reg['n_placebo_per_crisis']!r}"
    assert int(reg["n_placebo_per_crisis"]) == locked_n, _amsg
    summ = _summary()
    for wid, cnt in summ["counts"]["per_crisis"].items():
        _amsg2 = f"crisis {wid} must have exactly {locked_n} placebos; got {cnt}"
        assert int(cnt) == locked_n, _amsg2


# ---------------------------------------------------------------------------
# 8. Every placebo has a parent in CW3/CW4/CW5
# ---------------------------------------------------------------------------


def test_every_placebo_has_parent_crisis_in_cw3_cw4_cw5() -> None:
    reg = _registry()
    for p in reg["placebos"]:
        _amsg = (
            f"placebo {p['placebo_id']} parent {p['parent_crisis_window_id']!r} not in CW3/CW4/CW5"
        )
        assert p["parent_crisis_window_id"] in PRIMARY, _amsg
    total = len(reg["placebos"])
    _amsg2 = f"total placebos must be 3 x n_per; got {total}"
    assert total == 3 * int(reg["n_placebo_per_crisis"]), _amsg2


# ---------------------------------------------------------------------------
# 9. CRITICAL: no placebo overlaps ANY registered crisis window (CW1..CW6)
# ---------------------------------------------------------------------------


def test_no_placebo_overlaps_any_registered_crisis_window() -> None:
    reg = _registry()
    intervals = _registered_intervals()
    _amsg0 = f"must scan all six registered windows; got {len(intervals)}"
    assert len(intervals) == 6, _amsg0
    checked = 0
    for p in reg["placebos"]:
        ps = dt.date.fromisoformat(p["start_date"])
        pe = dt.date.fromisoformat(p["end_date"])
        for rid, rs, re_ in intervals:
            _amsg = (
                f"placebo {p['placebo_id']} [{ps}..{pe}] OVERLAPS registered "
                f"window {rid} buffered [{rs}..{re_}] -- fail-closed violation"
            )
            assert not _interval_overlap(ps, pe, rs, re_), _amsg
            checked += 1
        _amsg2 = f"placebo {p['placebo_id']} must self-declare non_overlap_verified true"
        assert p["non_overlap_verified"] is True, _amsg2
    _amsg3 = f"expected 6 overlap checks per placebo; did {checked}"
    assert checked == 6 * len(reg["placebos"]), _amsg3


# ---------------------------------------------------------------------------
# 10. Every placebo calendar length == its crisis (exact trading-day match)
# ---------------------------------------------------------------------------


def test_every_placebo_calendar_length_equals_its_crisis() -> None:
    crisis_len = {wid: load_crisis_window(wid).calendar_length_days for wid in PRIMARY}
    reg = _registry()
    for p in reg["placebos"]:
        parent = p["parent_crisis_window_id"]
        _amsg = (
            f"placebo {p['placebo_id']} calendar_length_days "
            f"{p['calendar_length_days']} != crisis {parent} length "
            f"{crisis_len[parent]} (exact trading-day match required)"
        )
        assert int(p["calendar_length_days"]) == crisis_len[parent], _amsg
    _amsg2 = "crisis lengths must be distinct enough to detect a mis-map (CW3=20, CW4=35, CW5=16)"
    assert crisis_len[CW3] == 20 and crisis_len[CW4] == 35 and crisis_len[CW5] == 16, _amsg2


# ---------------------------------------------------------------------------
# 11. Deterministic: run selector twice -> identical (anti-cherry-pick)
# ---------------------------------------------------------------------------


def test_placebo_selection_is_deterministic() -> None:
    pol = _k_p0_policy()
    for wid in PRIMARY:
        crisis = load_crisis_window(wid)
        run_a = select_matched_placebos(crisis, pol, LOCKED_SELECTION_SEED)
        run_b = select_matched_placebos(crisis, pol, LOCKED_SELECTION_SEED)
        a = [(p.placebo_id, p.start_date, p.end_date) for p in run_a]
        b = [(p.placebo_id, p.start_date, p.end_date) for p in run_b]
        _amsg = f"selector non-deterministic for {wid}: run A {a} != run B {b}"
        assert a == b, _amsg
        _amsg2 = f"selector must yield n_per placebos for {wid}; got {len(run_a)}"
        assert len(run_a) == int(pol["n_placebo_per_crisis"]), _amsg2


# ---------------------------------------------------------------------------
# 12. Selection seed is locked
# ---------------------------------------------------------------------------


def test_placebo_selection_seed_is_locked() -> None:
    reg = _registry()
    _amsg = f"registry selection_seed must equal locked seed {LOCKED_SELECTION_SEED}; got {reg.get('selection_seed')!r}"
    assert int(reg["selection_seed"]) == LOCKED_SELECTION_SEED, _amsg
    for p in reg["placebos"]:
        _amsg2 = f"placebo {p['placebo_id']} seed must equal locked seed {LOCKED_SELECTION_SEED}"
        assert int(p["seed"]) == LOCKED_SELECTION_SEED, _amsg2


# ---------------------------------------------------------------------------
# 13. Every placebo carries all five K-P0 match fields
# ---------------------------------------------------------------------------


def test_every_placebo_has_all_five_match_fields() -> None:
    reg = _registry()
    required = (
        "macro_period_class",
        "volatility_regime_bucket",
        "calendar_length_days",
        "data_availability_match",
        "baseline_variance_match",
    )
    for p in reg["placebos"]:
        for fld in required:
            _amsg = f"placebo {p['placebo_id']} missing match field {fld!r}"
            assert fld in p and p[fld] not in (None, ""), _amsg
        bvm = p["baseline_variance_match"]
        _amsg2 = f"placebo {p['placebo_id']} baseline_variance_match must report within_tolerance"
        assert "within_tolerance" in bvm, _amsg2


# ---------------------------------------------------------------------------
# 14. Negative: explicit date-overlap scan vs D-002J crisis dates
# ---------------------------------------------------------------------------


def test_no_placebo_inside_d002j_crisis_dates() -> None:
    reg = _load_json(CRISIS_REGISTRY_PATH)
    core_intervals = [
        (
            w["window_id"],
            dt.date.fromisoformat(w["start_date"]),
            dt.date.fromisoformat(w["end_date"]),
        )
        for w in reg["windows"]
    ]
    _amsg0 = f"must scan all six core crisis date ranges; got {len(core_intervals)}"
    assert len(core_intervals) == 6, _amsg0
    placebos = _registry()["placebos"]
    for p in placebos:
        ps = dt.date.fromisoformat(p["start_date"])
        pe = dt.date.fromisoformat(p["end_date"])
        for rid, rs, re_ in core_intervals:
            _amsg = (
                f"placebo {p['placebo_id']} [{ps}..{pe}] intersects core crisis {rid} [{rs}..{re_}]"
            )
            assert not _interval_overlap(ps, pe, rs, re_), _amsg


# ---------------------------------------------------------------------------
# 15. match_on fields == K-P0 policy exactly
# ---------------------------------------------------------------------------


def test_match_on_fields_equal_k_p0_policy() -> None:
    pol = _k_p0_policy()
    expected = [
        "macro_period",
        "volatility_regime",
        "calendar_length",
        "data_availability",
        "pre_window_baseline_variance",
    ]
    _amsg = f"K-P0 match_on lock must be {expected}; got {pol.get('match_on')!r}"
    assert list(pol["match_on"]) == expected, _amsg
    reg = _registry()
    _amsg2 = f"registry match_on must mirror K-P0 lock {expected}; got {reg.get('match_on')!r}"
    assert list(reg["match_on"]) == expected, _amsg2


# ---------------------------------------------------------------------------
# 16. Summary counts match registry
# ---------------------------------------------------------------------------


def test_summary_counts_match_registry() -> None:
    reg = _registry()
    summ = _summary()
    _amsg = f"summary total {summ['counts']['total']} != registry total {reg['total_placebos']}"
    assert int(summ["counts"]["total"]) == int(reg["total_placebos"]), _amsg
    per = {wid: 0 for wid in PRIMARY}
    for p in reg["placebos"]:
        per[p["parent_crisis_window_id"]] += 1
    _amsg2 = f"summary per_crisis {summ['counts']['per_crisis']} != recomputed {per}"
    assert summ["counts"]["per_crisis"] == per, _amsg2


# ---------------------------------------------------------------------------
# 17. Selection respects point-in-time boundary (no look-ahead vs K-P1)
# ---------------------------------------------------------------------------


def test_selection_respects_point_in_time_boundary() -> None:
    from research.systemic_risk.d002k_placebo_selection import PIT_DECISION_FRONTIER

    reg = _registry()
    for p in reg["placebos"]:
        pe = dt.date.fromisoformat(p["end_date"])
        _amsg = (
            f"placebo {p['placebo_id']} end {pe} runs past the point-in-time "
            f"decision frontier {PIT_DECISION_FRONTIER} -- look-ahead violation"
        )
        assert pe <= PIT_DECISION_FRONTIER, _amsg
    _amsg2 = "frontier must be a real date strictly before the 2026 decision date"
    assert PIT_DECISION_FRONTIER < dt.date(2026, 1, 1), _amsg2


# ---------------------------------------------------------------------------
# 18. No hand-picked / manual-override placebo flag
# ---------------------------------------------------------------------------


def test_no_hand_picked_placebo_flag() -> None:
    reg = _registry()
    raw = REGISTRY_PATH.read_text(encoding="utf-8").lower()
    for banned in ("manual_override", "hand_picked", "handpicked", "manually_selected"):
        _amsg = f"registry must not contain a {banned!r} override marker"
        assert banned not in raw, _amsg
    for p in reg["placebos"]:
        for key in p:
            _amsg2 = f"placebo {p['placebo_id']} carries forbidden override key {key!r}"
            assert "override" not in key.lower() and "manual" not in key.lower(), _amsg2


# ---------------------------------------------------------------------------
# 19. No systemic-risk prediction claim
# ---------------------------------------------------------------------------


def test_no_systemic_risk_prediction_claim() -> None:
    blobs = [
        REGISTRY_PATH.read_text(encoding="utf-8").lower(),
        SUMMARY_PATH.read_text(encoding="utf-8").lower(),
        DOC_PATH.read_text(encoding="utf-8").lower(),
    ]
    banned = ("predicts systemic", "forecasts the crisis", "predictive power proven")
    for blob in blobs:
        for phrase in banned:
            _amsg = f"forbidden systemic-risk prediction phrase {phrase!r} present"
            assert phrase not in blob, _amsg


# ---------------------------------------------------------------------------
# 20. No bank-level validation claim
# ---------------------------------------------------------------------------


def test_no_bank_level_validation_claim() -> None:
    blobs = [
        REGISTRY_PATH.read_text(encoding="utf-8").lower(),
        DOC_PATH.read_text(encoding="utf-8").lower(),
    ]
    banned = ("bank-level validated", "bank level validation", "validated at the bank")
    for blob in blobs:
        for phrase in banned:
            _amsg = f"forbidden bank-level validation phrase {phrase!r} present"
            assert phrase not in blob, _amsg


# ---------------------------------------------------------------------------
# 21. No D-002K prereg / contract edit (K-P0 + K-P1 byte-exact)
# ---------------------------------------------------------------------------


def test_no_d002k_prereg_edit() -> None:
    _amsg = f"K-P0 prereg sha drift: expected {D002K_PREREG_SHA}, got {_sha256(PREREG_PATH)}"
    assert _sha256(PREREG_PATH) == D002K_PREREG_SHA, _amsg
    _amsg2 = (
        f"D-002J prereg sha drift: expected {D002J_PREREG_SHA}, got {_sha256(D002J_PREREG_PATH)}"
    )
    assert _sha256(D002J_PREREG_PATH) == D002J_PREREG_SHA, _amsg2


# ---------------------------------------------------------------------------
# 22. No D-002J artifacts modified (incl. P2 crisis registry frozen)
# ---------------------------------------------------------------------------


def test_no_d002j_artifacts_modified() -> None:
    actual = _sha256(CRISIS_REGISTRY_PATH)
    _amsg = f"D-002J P2 crisis registry sha drift: expected {CRISIS_REGISTRY_SHA}, got {actual}"
    assert actual == CRISIS_REGISTRY_SHA, _amsg
    reg = _registry()
    _amsg2 = "registry must reference (not embed/edit) the frozen D-002J crisis registry path"
    assert reg["parent_crisis_registry_path"].startswith("artifacts/d002j/"), _amsg2


# ---------------------------------------------------------------------------
# 23. No canonical run authorized
# ---------------------------------------------------------------------------


def test_no_canonical_run_authorized() -> None:
    cap = _load_json(P2_VERDICT_PATH)
    _amsg = f"K-P2 capsule claim_boundary must assert canonical_run_authorized=false; got {cap['claim_boundary']!r}"
    assert "canonical_run_authorized=false" in cap["claim_boundary"], _amsg
    dag = _load_json(DAG_VERDICT_PATH)
    _amsg2 = "DAG canonical_run_authorized_anywhere must stay False"
    assert dag["canonical_run_authorized_anywhere"] is False, _amsg2


# ---------------------------------------------------------------------------
# 24. No unresolved merge markers
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [REGISTRY_PATH, SUMMARY_PATH, DOC_PATH, P2_VERDICT_PATH, SELECTOR_PATH]
    for path in targets:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            _amsg = f"unresolved merge marker in {path} at line {i}: {line!r}"
            assert not _MARKER.match(line), _amsg
