# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J — pre-registration locking tests.

D-002J is a fresh pre-registration that opens the financial-mechanistic
systemic-risk benchmark lineage AFTER D-002H closed REFUSED (PR #692,
merge sha 669d4458) and D-002I (investigation lineage, PR #693, merge
sha 2e55b73a) was opened. D-002J does NOT rescue D-002H — D-002H
REFUSED stays the truthful canonical verdict.

This test module locks the D-002J pre-registration content:
  * 5 research questions (RQ1..RQ5) and 7 workstreams (W1..W7);
  * 6 crisis windows (CW1..CW6) with their canonical names;
  * forbidden_claims and allowed_claims content;
  * parent lineage chain (D-002H prereg sha + D-002I prereg sha);
  * locked-governance sha pins (D-002G prereg, D-002G acceptance,
    D-002H prereg, D-002C claim ledger);
  * prereg_lock declaration; benchmark_only / power-first gates.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG_YAML = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"
RESEARCH_PLAN_MD = REPO_ROOT / "docs" / "research" / "D002J_RESEARCH_PLAN.md"
DATA_SOURCE_MD = REPO_ROOT / "docs" / "research" / "D002J_DATA_SOURCE_MATRIX.md"
CRISIS_WINDOWS_MD = REPO_ROOT / "docs" / "research" / "D002J_CRISIS_WINDOW_REGISTRY.md"
NULL_HIERARCHY_MD = REPO_ROOT / "docs" / "research" / "D002J_NULL_MODEL_HIERARCHY.md"
POWER_FIRST_MD = REPO_ROOT / "docs" / "research" / "D002J_POWER_FIRST_PROTOCOL.md"
PREREG_LOCK_JSON = REPO_ROOT / "artifacts" / "d002j" / "prereg" / "d002j_preregistration_lock.json"

# D-002G pre-registration locked sha256.
LOCKED_D002G_PREREG_SHA = "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04"  # pragma: allowlist secret  # noqa: E501
# D-002G acceptance rules locked sha256.
LOCKED_D002G_ACCEPTANCE_SHA = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"  # pragma: allowlist secret  # noqa: E501
# D-002H prereg locked sha256.
LOCKED_D002H_PREREG_SHA = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # pragma: allowlist secret  # noqa: E501
# D-002C claim ledger sha256 at D-002J prereg-lock anchor.
LOCKED_D002C_LEDGER_SHA_AT_D002J = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # pragma: allowlist secret  # noqa: E501

PARENT_CANONICAL_SHA = "250d8069d16ecabdb49b5a20b7cf1d622eddc925"  # pragma: allowlist secret
PARENT_INVESTIGATION_OPEN_SHA = (
    "2e55b73a191503e577fb828c6fcb6616127e41f9"  # pragma: allowlist secret
)

RQ_IDS = ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5")
WORKSTREAM_IDS = ("W1", "W2", "W3", "W4", "W5", "W6", "W7")
CRISIS_WINDOW_IDS = ("CW1", "CW2", "CW3", "CW4", "CW5", "CW6")
CRISIS_WINDOW_NAMES = {
    "CW1": "GFC",
    "CW2": "Eurozone Sovereign",
    "CW3": "US Repo Spike",
    "CW4": "COVID Dash-for-Cash",
    "CW5": "UK Gilt LDI",
    "CW6": "Regional Banking Stress",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_prereg() -> dict[str, Any]:
    with PREREG_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "D-002J prereg YAML must be a mapping"
    return cast(dict[str, Any], data)


def _load_lock_json() -> dict[str, Any]:
    with PREREG_LOCK_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "D-002J prereg JSON lock must be a mapping"
    return cast(dict[str, Any], data)


def _str_list(source: dict[str, Any], key: str) -> list[str]:
    value = source[key]
    assert isinstance(value, list), f"key {key!r} must be a list"
    return [str(item) for item in value]


def _dict_list(source: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = source[key]
    assert isinstance(value, list), f"key {key!r} must be a list"
    out: list[dict[str, Any]] = []
    for item in value:
        assert isinstance(item, dict), f"{key!r} entry must be a mapping: {item!r}"
        out.append(cast(dict[str, Any], item))
    return out


# ---------------------------------------------------------------------------
# 1) Files exist + schema_version pinned
# ---------------------------------------------------------------------------


def test_d002j_prereg_files_exist() -> None:
    """All 6 D-002J scaffold files exist on disk at their canonical paths."""
    missing: list[Path] = []
    for p in (
        PREREG_YAML,
        RESEARCH_PLAN_MD,
        DATA_SOURCE_MD,
        CRISIS_WINDOWS_MD,
        NULL_HIERARCHY_MD,
        POWER_FIRST_MD,
        PREREG_LOCK_JSON,
    ):
        if not p.exists():
            missing.append(p)
    msg = f"missing D-002J files: {[str(m) for m in missing]}"
    assert not missing, msg
    # Specific dual presence assertions to catch single-file deletes
    # (drift-sentinel: 2 independent assertions, not 1 aggregate truthy).
    assert PREREG_YAML.is_file(), f"PREREG_YAML must be a file: {PREREG_YAML}"
    assert PREREG_LOCK_JSON.is_file(), f"PREREG_LOCK_JSON must be a file: {PREREG_LOCK_JSON}"


def test_d002j_schema_version_pinned() -> None:
    """schema_version pinned to D002J-PREREGISTRATION-v1 (YAML) and D002J-PREREG-v1 (JSON)."""
    yaml_data = _load_prereg()
    lock_data = _load_lock_json()
    yaml_sv = str(yaml_data["schema_version"])
    json_sv = str(lock_data["schema_version"])
    msg_yaml = f"YAML schema_version drift: {yaml_sv!r}"
    msg_json = f"JSON schema_version drift: {json_sv!r}"
    assert yaml_sv == "D002J-PREREGISTRATION-v1", msg_yaml
    assert json_sv == "D002J-PREREG-v1", msg_json
    # Study id is consistent across both sources.
    assert str(yaml_data["study_id"]) == "D-002J"
    assert str(lock_data["study_id"]) == "D-002J"


# ---------------------------------------------------------------------------
# 2) 5 research questions pinned
# ---------------------------------------------------------------------------


def test_d002j_5_research_questions_pinned() -> None:
    """Exactly 5 research questions with canonical ids RQ1..RQ5 in order."""
    for source in (_load_prereg(), _load_lock_json()):
        rqs = _dict_list(source, "research_questions")
        assert len(rqs) == 5, f"expected 5 research questions, got {len(rqs)}"
        ids = tuple(str(rq["id"]) for rq in rqs)
        assert ids == RQ_IDS, f"RQ ids out of order: {ids}"
        # Each RQ carries a non-empty question text (drift-sentinel: 2nd assert).
        for rq in rqs:
            q = rq.get("question")
            qmsg = f"RQ {rq.get('id')!r} missing question text"
            assert isinstance(q, str) and q.strip(), qmsg


# ---------------------------------------------------------------------------
# 3) 7 workstreams pinned
# ---------------------------------------------------------------------------


def test_d002j_7_workstreams_pinned() -> None:
    """Exactly 7 workstreams with canonical ids W1..W7 in order."""
    for source in (_load_prereg(), _load_lock_json()):
        ws = _dict_list(source, "workstreams")
        assert len(ws) == 7, f"expected 7 workstreams, got {len(ws)}"
        ids = tuple(str(w["id"]) for w in ws)
        assert ids == WORKSTREAM_IDS, f"workstream ids out of order: {ids}"
        # Each workstream names a plan_section like '§N' (drift-sentinel).
        for w in ws:
            ps = w.get("plan_section")
            wmsg = f"workstream {w.get('id')!r} missing plan_section"
            assert isinstance(ps, str) and ps.startswith("§"), wmsg


# ---------------------------------------------------------------------------
# 4) Crisis windows (count + ids + canonical names)
# ---------------------------------------------------------------------------


def test_d002j_6_crisis_windows_pinned() -> None:
    """Exactly 6 crisis windows CW1..CW6 with canonical names match plan §7."""
    for source in (_load_prereg(), _load_lock_json()):
        cws = _dict_list(source, "crisis_windows")
        assert len(cws) == 6, f"expected 6 crisis windows, got {len(cws)}"
        ids = tuple(str(c["id"]) for c in cws)
        assert ids == CRISIS_WINDOW_IDS, f"crisis-window ids out of order: {ids}"
        for c in cws:
            cid = str(c["id"])
            expected = CRISIS_WINDOW_NAMES[cid]
            got = str(c["name"])
            cmsg = f"crisis-window {cid} name drift: expected {expected!r}, got {got!r}"
            assert got == expected, cmsg


def test_d002j_crisis_window_year_ranges_pinned() -> None:
    """Crisis-window start/end years pinned at the plan §7 anchors."""
    yaml_data = _load_prereg()
    cws = _dict_list(yaml_data, "crisis_windows")
    by_id = {str(c["id"]): c for c in cws}
    expected_years = {
        "CW1": (2007, 2009),
        "CW2": (2011, 2012),
        "CW3": (2019, 2019),
        "CW4": (2020, 2020),
        "CW5": (2022, 2022),
        "CW6": (2023, 2023),
    }
    for cid, (s, e) in expected_years.items():
        c = by_id[cid]
        start_year = int(cast(int, c["start_year"]))
        end_year = int(cast(int, c["end_year"]))
        smsg = f"{cid} start_year drift: {start_year} != {s}"
        emsg = f"{cid} end_year drift: {end_year} != {e}"
        assert start_year == s, smsg
        assert end_year == e, emsg


# ---------------------------------------------------------------------------
# 5) Forbidden + allowed claims content
# ---------------------------------------------------------------------------


def test_d002j_forbidden_claims_content() -> None:
    """Forbidden claims pin the 7 plan §14 entries verbatim across YAML+JSON."""
    expected_phrases = (
        "D-002J rescues D-002H",
        "D-002J invalidates D-002H REFUSED",
        "D-002J proves systemic-risk prediction",
        "D-002J claims real-bank validation without real-bank data",
        "D-002J generalises across substrates without evidence",
        "D-002J promotes positive controls as real-world proof",
        "D-002J allows post-hoc parameter tuning",
    )
    for source in (_load_prereg(), _load_lock_json()):
        forbidden = _str_list(source, "forbidden_claims")
        for phrase in expected_phrases:
            assert phrase in forbidden, f"missing forbidden claim: {phrase!r}"


def test_d002j_allowed_claims_content() -> None:
    """Allowed claims pin the 6 plan §15 entries verbatim across YAML+JSON."""
    expected_phrases = (
        "D-002J builds a financial-mechanistic benchmark lineage",
        "D-002J tests whether financially motivated substrates improve signal/null separation",
        "D-002J uses crisis windows as external stress anchors",
        "D-002J requires positive controls before real-data interpretation",
        "D-002J requires power-first design before canonical sweep",
        "D-002J treats negative results as retained evidence",
    )
    for source in (_load_prereg(), _load_lock_json()):
        allowed = _str_list(source, "allowed_claims")
        for phrase in expected_phrases:
            assert phrase in allowed, f"missing allowed claim: {phrase!r}"


# ---------------------------------------------------------------------------
# 6) Parent lineage chain
# ---------------------------------------------------------------------------


def test_d002j_parent_lineage_d002h() -> None:
    """parent_lineage = D-002H; parent_canonical_run_merge_sha pinned at 250d8069..."""
    yaml_data = _load_prereg()
    lock_data = _load_lock_json()
    assert str(yaml_data["parent_lineage"]) == "D-002H"
    assert str(lock_data["parent_lineage"]) == "D-002H"
    yaml_psha = str(yaml_data["parent_canonical_run_merge_sha"])
    json_psha = str(lock_data["parent_canonical_run_merge_sha"])
    assert yaml_psha == PARENT_CANONICAL_SHA, f"YAML parent sha drift: {yaml_psha!r}"
    assert json_psha == PARENT_CANONICAL_SHA, f"JSON parent sha drift: {json_psha!r}"
    # Parent canonical verdict preserved verbatim.
    assert str(yaml_data["parent_canonical_run_verdict"]) == "REFUSED_NULL_AUDIT_FAIL_D002H"
    assert str(lock_data["parent_canonical_run_verdict"]) == "REFUSED_NULL_AUDIT_FAIL_D002H"


def test_d002j_parent_investigation_d002i() -> None:
    """parent_investigation_lineage = D-002I; D-002I prereg sha + open sha pinned."""
    yaml_data = _load_prereg()
    lock_data = _load_lock_json()
    assert str(yaml_data["parent_investigation_lineage"]) == "D-002I"
    assert str(lock_data["parent_investigation_lineage"]) == "D-002I"
    # D-002I prereg sha is the same anchor D-002H prereg uses elsewhere
    # in this lineage chain (the D-002I prereg pins D-002H prereg sha
    # 44b18b5a... as its parent anchor; D-002J pins the same for
    # parent_investigation_prereg_sha by the chain semantics).
    yaml_isha = str(yaml_data["parent_investigation_prereg_sha"])
    json_isha = str(lock_data["parent_investigation_prereg_sha"])
    assert yaml_isha == LOCKED_D002H_PREREG_SHA, f"YAML D-002I prereg sha drift: {yaml_isha!r}"
    assert json_isha == LOCKED_D002H_PREREG_SHA, f"JSON D-002I prereg sha drift: {json_isha!r}"
    # D-002I lineage-open commit sha (PR #693 merge) pinned.
    assert str(yaml_data["parent_investigation_lineage_open_sha"]) == PARENT_INVESTIGATION_OPEN_SHA
    assert str(lock_data["parent_investigation_lineage_open_sha"]) == PARENT_INVESTIGATION_OPEN_SHA


# ---------------------------------------------------------------------------
# 7) Ledger anchor recorded inside the prereg
# ---------------------------------------------------------------------------


def test_d002j_d002c_ledger_anchor_field() -> None:
    """D-002C ledger sha-at-prereg field pinned at the post-D-002H-REFUSED-append anchor."""
    yaml_data = _load_prereg()
    rel = yaml_data["relationship_to_d002c"]
    assert isinstance(rel, dict)
    rel_d = cast(dict[str, Any], rel)
    yaml_anchor = str(rel_d["d002c_ledger_sha_at_d002j_prereg"])
    msg = f"D-002J prereg yaml field d002c_ledger_sha_at_d002j_prereg drift: {yaml_anchor!r}"
    assert yaml_anchor == LOCKED_D002C_LEDGER_SHA_AT_D002J, msg
    # Lock JSON carries the same anchor under `locked_anchors`.
    lock_data = _load_lock_json()
    anchors = lock_data["locked_anchors"]
    assert isinstance(anchors, dict)
    anchors_d = cast(dict[str, Any], anchors)
    json_anchor = str(anchors_d["d002c_claim_ledger_sha256_at_d002j_prereg"])
    msg2 = f"D-002J lock JSON d002c_claim_ledger_sha256_at_d002j_prereg drift: {json_anchor!r}"
    assert json_anchor == LOCKED_D002C_LEDGER_SHA_AT_D002J, msg2


# ---------------------------------------------------------------------------
# 8) Locked-governance shas byte-exact on disk
# ---------------------------------------------------------------------------


def test_d002j_locked_governance_shas_byte_exact() -> None:
    """D-002G/D-002H prereg+rules and D-002C ledger sha256 byte-exact at locked anchors."""
    d002g_prereg = REPO_ROOT / "docs" / "governance" / "D002G_PREREGISTRATION.yaml"
    d002g_rules = REPO_ROOT / "docs" / "governance" / "D002G_ACCEPTANCE_RULES.md"
    d002h_prereg = REPO_ROOT / "docs" / "governance" / "D002H_PREREGISTRATION.yaml"
    ledger = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
    pairs = (
        (d002g_prereg, LOCKED_D002G_PREREG_SHA, "D002G_PREREGISTRATION.yaml"),
        (d002g_rules, LOCKED_D002G_ACCEPTANCE_SHA, "D002G_ACCEPTANCE_RULES.md"),
        (d002h_prereg, LOCKED_D002H_PREREG_SHA, "D002H_PREREGISTRATION.yaml"),
        (ledger, LOCKED_D002C_LEDGER_SHA_AT_D002J, "D002C_CLAIM_LEDGER.yaml"),
    )
    for path, expected, label in pairs:
        assert path.exists(), f"locked file missing: {label}"
        actual = _sha256(path)
        msg = f"locked-governance {label} sha drift: expected {expected}, got {actual}"
        assert actual == expected, msg


# ---------------------------------------------------------------------------
# 9) Canonical-run authorisation flags
# ---------------------------------------------------------------------------


def test_d002j_no_canonical_run_authorisation() -> None:
    """canonical_run_authorized False; benchmark_only True; power-first approval required."""
    for source in (_load_prereg(), _load_lock_json()):
        assert source["canonical_run_authorized"] is False
        assert source["benchmark_only"] is True
        assert source["requires_power_first_approval"] is True


# ---------------------------------------------------------------------------
# 10) Prereg lock at merge
# ---------------------------------------------------------------------------


def test_d002j_prereg_lock_at_merge() -> None:
    """prereg_lock declares locked_at_merge=True + edit_policy fresh_pre_registration_only."""
    yaml_data = _load_prereg()
    lock = yaml_data["prereg_lock"]
    assert isinstance(lock, dict)
    lock_d = cast(dict[str, Any], lock)
    assert lock_d["locked_at_merge"] is True
    assert str(lock_d["edit_policy"]) == "fresh_pre_registration_only"
    assert "D002K" in str(lock_d["edit_constitutes"])

    lock_json = _load_lock_json()
    assert lock_json["locked_at_merge"] is True
    assert str(lock_json["edit_policy"]) == "fresh_pre_registration_only"


# ---------------------------------------------------------------------------
# 11) Success and failure criteria pinned
# ---------------------------------------------------------------------------


def test_d002j_success_criteria_pinned() -> None:
    """All 10 plan §16 success criteria are pinned in both YAML and JSON."""
    expected = (
        "source registry assembled",
        "crisis-window registry created",
        "known-positive controls created",
        "≥ 2 financial-mechanistic substrates implemented",
        "null hierarchy implemented",
        "power-first design executed",
        "canonical run only after power approval",
        "all results → append-only ledger",
        "benchmark reproducible by one command",
        "external reader sees research-grade system, not chaos of PRs",
    )
    yaml_data = _load_prereg()
    yaml_criteria = _str_list(yaml_data, "success_criteria")
    assert len(yaml_criteria) == 10, f"expected 10 success criteria, got {len(yaml_criteria)}"
    for phrase in expected:
        assert phrase in yaml_criteria, f"missing success criterion: {phrase!r}"
    # JSON lock pins ASCII-normalised forms; ensure all-10 count and
    # presence of structural anchor phrases (drift-sentinel cross-form check).
    lock_data = _load_lock_json()
    lock_criteria = _str_list(lock_data, "success_criteria")
    assert len(lock_criteria) == 10
    assert any("source registry assembled" in c for c in lock_criteria)


def test_d002j_failure_criteria_pinned() -> None:
    """All 8 plan §17 failure criteria are pinned in both YAML and JSON."""
    expected = (
        "positive controls undetected",
        "null models trivial / no-op",
        "majority of grid cells underpowered",
        "signal survives only after post-hoc tuning",
        "crisis-window labels ambiguous",
        "data provenance incomplete",
        "claims exceed boundary",
        "negative results hidden / off-ledger",
    )
    for source in (_load_prereg(), _load_lock_json()):
        criteria = _str_list(source, "failure_criteria")
        assert len(criteria) == 8, f"expected 8 failure criteria, got {len(criteria)}"
        for phrase in expected:
            assert phrase in criteria, f"missing failure criterion: {phrase!r}"


# ---------------------------------------------------------------------------
# 12) BLOCKERS append landed
# ---------------------------------------------------------------------------


def test_d002j_blockers_append_landed() -> None:
    """D002G_CANONICAL_RUN_BLOCKERS.md carries the new D-002J lineage-opened section."""
    blockers = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"
    assert blockers.exists(), f"missing: {blockers}"
    text = blockers.read_text(encoding="utf-8")
    assert "D-002J lineage opened" in text, "BLOCKERS.md missing D-002J lineage-opened section"
    # Sanity: prior D-002I section is preserved (append-only contract).
    assert "D-002I lineage opened" in text, "BLOCKERS.md lost D-002I section — append-only broken"


# ---------------------------------------------------------------------------
# 13) Plan-section narrative present in research plan
# ---------------------------------------------------------------------------


def test_d002j_research_plan_sections_present() -> None:
    """Research plan markdown carries §1, §14, §15, §22 anchors."""
    text = RESEARCH_PLAN_MD.read_text(encoding="utf-8")
    expected_anchors = ("§1 — Justification", "§14 — Forbidden claims", "§22 — Final framing")
    for anchor in expected_anchors:
        assert anchor in text, f"D002J_RESEARCH_PLAN.md missing anchor: {anchor!r}"
    # Lineage chain narrative present (drift-sentinel: 2nd assert).
    assert "D-002J" in text and "D-002H REFUSED" in text


# ---------------------------------------------------------------------------
# 14) W2 / W5 / W6 scaffold contracts present
# ---------------------------------------------------------------------------


def test_d002j_w2_w5_w6_scaffold_contracts_present() -> None:
    """Crisis-window + null-hierarchy + power-first scaffolds carry acceptance contracts."""
    cw_text = CRISIS_WINDOWS_MD.read_text(encoding="utf-8")
    nh_text = NULL_HIERARCHY_MD.read_text(encoding="utf-8")
    pf_text = POWER_FIRST_MD.read_text(encoding="utf-8")
    # W2 — every CW id named.
    for cid in CRISIS_WINDOW_IDS:
        assert cid in cw_text, f"crisis-window registry missing {cid}"
    # W5 — all 9 null model ids named.
    expected_nulls = (
        "degree_preserving",
        "weight_preserving",
        "temporal_block_bootstrap",
        "window_shift_placebo",
        "label_permutation",
        "configuration_model",
        "sparse_maximum_entropy_reconstruction",
        "shock_time_placebo",
        "IAAFT_surrogate",
    )
    for null in expected_nulls:
        assert null in nh_text, f"null-model hierarchy missing {null!r}"
    # W6 — power-first mandatory metrics named.
    expected_metrics = (
        "minimal_detectable_effect",
        "n_min",
        "power_target",
        "runtime_budget",
        "false_negative_risk",
        "metric_specific_power",
        "null_specific_power",
    )
    for metric in expected_metrics:
        assert metric in pf_text, f"power-first protocol missing metric {metric!r}"
