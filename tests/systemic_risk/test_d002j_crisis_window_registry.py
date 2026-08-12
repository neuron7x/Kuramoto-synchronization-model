# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P2 — crisis window registry v1 fail-closed tests.

16 P2 guard tests enforcing the registry contract from the operator's
master document. Every test contains >= 2 assertions or >= 2 distinct
cases. Drift sentinels for byte-exact locked governance shas, for
phase-coupling to P1B audit-surviving sources, and for forbidden-
claim boundary preservation are included.

P2 is registry-only: assembles 6 windows on top of P1B-surviving
sources (audit_status VERIFIED or PARTIAL). NO ingestion, NO modeling,
NO substrate, NO null execution, NO canonical run, NO prediction
claim, NO bank-level validation, NO cross-asset/interbank overclaim.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, cast

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
REGISTRY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "crisis_windows" / "crisis_window_registry_v1.json"
)
SUMMARY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "crisis_windows" / "crisis_window_summary_v1.json"
)
REGISTRY_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_CRISIS_WINDOW_REGISTRY.md"
RATIONALE_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_CRISIS_WINDOW_SELECTION_RATIONALE.md"
P1B_REGISTRY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_registry_v1.json"
)
P1B_AUDIT_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_provenance_audit_v1.json"
)
BLOCKERS_MD: Path = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"
ACCEPTOR_YAML: Path = (
    REPO_ROOT / ".claude" / "commit_acceptors" / "x10r-d002j-p2-crisis-window-registry.yaml"
)
D002J_PREREG: Path = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"
RESEARCH_SYSTEMIC_DIR: Path = REPO_ROOT / "research" / "systemic_risk"

# Locked governance sha256 pins (byte-exact at P2 PR open).
# Split into two halves so the line stays under 100 chars without
# triggering black-vs-ruff format wrap conflicts.
LOCKED_D002C_LEDGER_SHA: str = (  # pragma: allowlist secret
    "eb0b7151d76e5409e6dc9bb4a023551de" + "5e0704673d5ac9f726319ef84a32387"
)
LOCKED_D002G_PREREG_SHA: str = (  # pragma: allowlist secret
    "1ab91f09370e4705a8b0849467bc1f56d" + "f2e58d58d5623d3b6d905cbd110bb04"
)
LOCKED_D002G_ACCEPTANCE_SHA: str = (  # pragma: allowlist secret
    "875b1e3eb031b8e5333dc8b455454f0a3" + "0419ead1ebe787aa01d5882e7d6ad31"
)
LOCKED_D002H_PREREG_SHA: str = (  # pragma: allowlist secret
    "44b18b5a40ce9d188a9c3bd49339621f8" + "1a65a15f97a683247902450dd54acec"
)
LOCKED_D002I_PREREG_SHA: str = (  # pragma: allowlist secret
    "b646989c032dc0e29f9b791e0b68209ff" + "22b40f4757737712badc8656cf2db5f"
)
LOCKED_D002J_PREREG_SHA: str = (  # pragma: allowlist secret
    "f3dc65b7e64b96eafe6f23ca8bdd0e05d" + "c9bf95b12c2658b227bd0340f7975a0"
)
LOCKED_P1B_REGISTRY_SHA: str = (  # pragma: allowlist secret
    "f1899b7a882b4b3efbebb54e3dc942c07" + "9839f77f981273e2dd09757973b14ec"
)

VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "systemic_banking_crisis",
        "sovereign_debt_crisis",
        "repo_market_dysfunction",
        "liquidity_crisis",
        "gilt_dysfunction",
        "regional_banking_crisis",
    }
)
VALID_MECHANISM_FAMILIES: frozenset[str] = frozenset(
    {
        "balance_sheet",
        "liquidity_funding",
        "contagion",
        "market_wide_stress",
        "official_response",
        "information_constraint",
    }
)
EXPECTED_WINDOW_IDS: tuple[str, ...] = (
    "CW1_GFC_2007_2009",
    "CW2_EUROZONE_2011_2012",
    "CW3_US_REPO_SPIKE_2019",
    "CW4_COVID_DASH_FOR_CASH_2020",
    "CW5_UK_GILT_LDI_2022",
    "CW6_REGIONAL_BANKING_2023",
)

# Forbidden-claim regex patterns. Each MUST appear ONLY inside a
# forbidden_use, claim_boundary, exclusion_notes, or otherwise
# explicitly-negated context (the negative-declaration buffer).
PREDICTION_PATTERNS: tuple[str, ...] = (
    r"predicts\s+crisis",
    r"systemic\s+prediction",
    r"crisis\s+prediction",
)
BANK_LEVEL_PATTERNS: tuple[str, ...] = (
    r"bank[-\s]level\s+validated",
    r"real[-\s]bank\s+confirmed",
)
INGESTION_PATTERNS: tuple[str, ...] = (
    r"\bingested\b",
    r"downloaded\s+raw\b",
)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _surviving_source_ids() -> tuple[set[str], dict[str, str]]:
    """Return (set of P1B VERIFIED|PARTIAL source_ids, status map)."""
    audit = _load_json(P1B_AUDIT_JSON)
    sources = cast(list[dict[str, Any]], audit["sources"])
    status_map: dict[str, str] = {
        cast(str, s["source_id"]): cast(str, s["audit_status"]) for s in sources
    }
    surviving: set[str] = {sid for sid, st in status_map.items() if st in ("VERIFIED", "PARTIAL")}
    return surviving, status_map


def _p2_source_ids_by_window() -> dict[str, list[str]]:
    reg = _load_json(REGISTRY_JSON)
    windows = cast(list[dict[str, Any]], reg["windows"])
    return {cast(str, w["window_id"]): cast(list[str], w["source_ids"]) for w in windows}


def _all_p2_source_ids() -> set[str]:
    out: set[str] = set()
    for ids in _p2_source_ids_by_window().values():
        out.update(ids)
    return out


def _claim_strict_files() -> tuple[Path, ...]:
    """Files where forbidden phrases must NOT appear at all.

    The registry JSON and the two markdown documents ARE the forbidden-
    claim declaration surface — they explicitly negate the forbidden
    phrases inside `forbidden_use` blocks, `claim_boundary` blocks,
    `exclusion_notes`, and `forbidden_interpretations` sections; these
    files are therefore EXCLUDED from the strict scan. The summary JSON
    is a pure decision artifact and may NOT contain the forbidden
    phrases at all.
    """
    return (SUMMARY_JSON,)


def test_p2_only_uses_p1b_verified_or_partial_sources() -> None:
    """Phase-coupling: every P2 source_id must come from P1B surviving set (no DOWNGRADED, no REJECTED)."""
    surviving, status_map = _surviving_source_ids()
    p2_ids = _all_p2_source_ids()
    not_surviving = p2_ids - surviving
    msg_not_surviving = (
        f"P2 references {len(not_surviving)} sources outside P1B surviving "
        f"(VERIFIED|PARTIAL) set: {sorted(not_surviving)}; "
        "promotion of DOWNGRADED or REJECTED source is forbidden"
    )
    assert not not_surviving, msg_not_surviving
    bad_status: dict[str, str] = {
        sid: status_map[sid] for sid in p2_ids if status_map.get(sid) in ("DOWNGRADED", "REJECTED")
    }
    msg_bad_status = (
        f"P2 references {len(bad_status)} sources with DOWNGRADED|REJECTED status: "
        f"{bad_status}; all P2 sources must be VERIFIED or PARTIAL"
    )
    assert not bad_status, msg_bad_status


def test_no_p2_source_id_missing_from_p1b_registry() -> None:
    """Every P2 source_id must exist in the P1B registry's source_id keyspace."""
    p1b = _load_json(P1B_REGISTRY_JSON)
    p1b_ids: set[str] = {
        cast(str, s["source_id"]) for s in cast(list[dict[str, Any]], p1b["sources"])
    }
    p2_ids = _all_p2_source_ids()
    missing = p2_ids - p1b_ids
    msg_missing = (
        f"P2 references {len(missing)} source_ids not in P1B registry: {sorted(missing)}; "
        f"P1B registry has {len(p1b_ids)} declared source_ids; "
        "every P2 binding must reach a declared P1B source"
    )
    assert not missing, msg_missing
    # Distinct second case: P1B-surviving set must be a superset of P2 set
    surviving, _ = _surviving_source_ids()
    msg_subset = (
        f"P2 source set ({len(p2_ids)}) must be subset of P1B-surviving set ({len(surviving)})"
    )
    assert p2_ids <= surviving, msg_subset


def test_no_p2_source_id_from_downgraded_or_rejected_sources() -> None:
    """Explicit blacklist check: no DOWNGRADED, no REJECTED source promoted to a P2 window."""
    _, status_map = _surviving_source_ids()
    downgraded_set: set[str] = {sid for sid, st in status_map.items() if st == "DOWNGRADED"}
    rejected_set: set[str] = {sid for sid, st in status_map.items() if st == "REJECTED"}
    p2_ids = _all_p2_source_ids()
    bad_downgraded = p2_ids & downgraded_set
    msg_dg = (
        f"P2 references {len(bad_downgraded)} DOWNGRADED sources: {sorted(bad_downgraded)}; "
        "blacklist invariant violated"
    )
    assert not bad_downgraded, msg_dg
    bad_rejected = p2_ids & rejected_set
    msg_rj = (
        f"P2 references {len(bad_rejected)} REJECTED sources: {sorted(bad_rejected)}; "
        "blacklist invariant violated"
    )
    assert not bad_rejected, msg_rj


def test_each_window_has_minimum_three_p1b_surviving_sources() -> None:
    """Per-window floor: len(source_ids) >= 3 and every binding is P1B-surviving."""
    surviving, _ = _surviving_source_ids()
    windows = _p2_source_ids_by_window()
    msg_count_windows = (
        f"P2 registry must declare exactly 6 windows; observed "
        f"{len(windows)}; window ids: {sorted(windows)}"
    )
    assert len(windows) == 6, msg_count_windows
    short_windows: dict[str, int] = {wid: len(ids) for wid, ids in windows.items() if len(ids) < 3}
    msg_short = (
        f"{len(short_windows)} window(s) carry fewer than 3 source_ids: "
        f"{short_windows}; per-window floor 3 violated"
    )
    assert not short_windows, msg_short
    non_surviving_per_window: dict[str, list[str]] = {}
    for wid, ids in windows.items():
        bad = sorted(set(ids) - surviving)
        if bad:
            non_surviving_per_window[wid] = bad
    msg_bad = (
        f"{len(non_surviving_per_window)} window(s) contain non-P1B-surviving "
        f"source_ids: {non_surviving_per_window}"
    )
    assert not non_surviving_per_window, msg_bad


def test_each_window_has_expected_observable_signature() -> None:
    """Non-empty `expected_observable_signature` per window; non-empty primary_observables list."""
    reg = _load_json(REGISTRY_JSON)
    bad_sig: list[str] = []
    bad_primary: list[str] = []
    for w in cast(list[dict[str, Any]], reg["windows"]):
        wid = cast(str, w["window_id"])
        sig = cast(str, w.get("expected_observable_signature", "")).strip()
        if not sig:
            bad_sig.append(wid)
        prim = cast(list[str], w.get("primary_observables", []))
        if not prim:
            bad_primary.append(wid)
    msg_sig = f"{len(bad_sig)} window(s) missing expected_observable_signature: {bad_sig}"
    assert not bad_sig, msg_sig
    msg_primary = f"{len(bad_primary)} window(s) missing primary_observables: {bad_primary}"
    assert not bad_primary, msg_primary


def test_each_window_has_mechanism_family_mapping() -> None:
    """primary_mechanism_family must be a valid enum; secondary list a subset of enum."""
    reg = _load_json(REGISTRY_JSON)
    bad_primary: list[tuple[str, str]] = []
    bad_secondary: dict[str, list[str]] = {}
    for w in cast(list[dict[str, Any]], reg["windows"]):
        wid = cast(str, w["window_id"])
        prim = cast(str, w.get("primary_mechanism_family", ""))
        if prim not in VALID_MECHANISM_FAMILIES:
            bad_primary.append((wid, prim))
        sec = cast(list[str], w.get("secondary_mechanism_families", []))
        bad = [m for m in sec if m not in VALID_MECHANISM_FAMILIES]
        if bad:
            bad_secondary[wid] = bad
    msg_prim = (
        f"{len(bad_primary)} window(s) carry invalid primary_mechanism_family: "
        f"{bad_primary}; allowed = {sorted(VALID_MECHANISM_FAMILIES)}"
    )
    assert not bad_primary, msg_prim
    msg_sec = (
        f"{len(bad_secondary)} window(s) carry invalid secondary_mechanism_families "
        f"entries: {bad_secondary}; allowed = {sorted(VALID_MECHANISM_FAMILIES)}"
    )
    assert not bad_secondary, msg_sec


def test_each_window_has_valid_date_bounds() -> None:
    """start_date < end_date; pre_event_buffer <= start_date; post_event_buffer >= end_date; valid ISO-8601."""
    reg = _load_json(REGISTRY_JSON)
    bad_iso: list[tuple[str, str, str]] = []
    bad_order: list[tuple[str, str, str]] = []
    bad_buffer: list[tuple[str, str, str, str, str]] = []
    for w in cast(list[dict[str, Any]], reg["windows"]):
        wid = cast(str, w["window_id"])
        sd_str = cast(str, w["start_date"])
        ed_str = cast(str, w["end_date"])
        pre_str = cast(str, w["pre_event_buffer"])
        post_str = cast(str, w["post_event_buffer"])
        parsed: dict[str, date] = {}
        for field, val in (
            ("start_date", sd_str),
            ("end_date", ed_str),
            ("pre_event_buffer", pre_str),
            ("post_event_buffer", post_str),
        ):
            try:
                parsed[field] = date.fromisoformat(val)
            except ValueError:
                bad_iso.append((wid, field, val))
        if "start_date" in parsed and "end_date" in parsed:
            if not parsed["start_date"] < parsed["end_date"]:
                bad_order.append((wid, sd_str, ed_str))
        if all(
            k in parsed for k in ("start_date", "end_date", "pre_event_buffer", "post_event_buffer")
        ):
            if (
                parsed["pre_event_buffer"] > parsed["start_date"]
                or parsed["post_event_buffer"] < parsed["end_date"]
            ):
                bad_buffer.append((wid, pre_str, sd_str, ed_str, post_str))
    msg_iso = f"{len(bad_iso)} invalid ISO-8601 date(s): {bad_iso}"
    assert not bad_iso, msg_iso
    msg_order = f"{len(bad_order)} window(s) with start_date >= end_date: {bad_order}"
    assert not bad_order, msg_order
    msg_buf = (
        f"{len(bad_buffer)} window(s) with mis-ordered buffers (need pre<=start, post>=end): "
        f"{bad_buffer}"
    )
    assert not bad_buffer, msg_buf


def _scan_strict_for(patterns: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Scan strict files (summary JSON) for any occurrence of the patterns.

    Returns list of (file, pattern, snippet) tuples; empty if clean.
    Strict files are NOT permitted to contain forbidden phrases at all,
    even inside negation contexts — these files are decision artifacts,
    not declaration documents.
    """
    leaks: list[tuple[str, str, str]] = []
    for path in _claim_strict_files():
        text_lower = path.read_text(encoding="utf-8").lower()
        for pat in patterns:
            for match in re.finditer(pat, text_lower):
                snippet = text_lower[max(0, match.start() - 60) : match.end() + 60]
                leaks.append((str(path), pat, snippet))
    return leaks


def test_no_prediction_claim() -> None:
    """No 'predicts crisis' / 'systemic prediction' / 'crisis prediction' affirmatives in strict files."""
    leaks = _scan_strict_for(PREDICTION_PATTERNS)
    msg_leak = (
        f"{len(leaks)} prediction-claim leak(s) in strict (non-declaration) "
        f"P2 file(s): {leaks[:3]}; declaration files (registry JSON / MD) may "
        "carry the forbidden phrases inside negation contexts only"
    )
    assert not leaks, msg_leak
    # Distinct second case: registry.json must declare prediction-claim-forbidden,
    # AND its declaration block MUST list each forbidden phrase verbatim
    reg = _load_json(REGISTRY_JSON)
    scope = cast(dict[str, Any], reg.get("registry_scope", {}))
    msg_flag = (
        f"registry_scope.prediction_claim_forbidden must be True; got "
        f"{scope.get('prediction_claim_forbidden')!r}"
    )
    assert scope.get("prediction_claim_forbidden") is True, msg_flag
    forbidden_block = " ".join(cast(list[str], reg.get("forbidden_use", []))).lower()
    missing = [p for p in ("predicts crisis", "crisis prediction") if p not in forbidden_block]
    msg_block = (
        f"forbidden_use block missing canonical phrase(s): {missing}; "
        f"observed block contents: {forbidden_block!r}"
    )
    assert not missing, msg_block


def test_no_bank_level_validation_claim() -> None:
    """No 'bank-level validated' / 'real-bank confirmed' affirmatives in strict files."""
    leaks = _scan_strict_for(BANK_LEVEL_PATTERNS)
    msg_leak = (
        f"{len(leaks)} bank-level-validation-claim leak(s) in strict "
        f"(non-declaration) P2 file(s): {leaks[:3]}"
    )
    assert not leaks, msg_leak
    # Distinct second case: registry.json must declare bank-level-validation-forbidden
    reg = _load_json(REGISTRY_JSON)
    scope = cast(dict[str, Any], reg.get("registry_scope", {}))
    msg_flag = (
        f"registry_scope.bank_level_validation_forbidden must be True; got "
        f"{scope.get('bank_level_validation_forbidden')!r}"
    )
    assert scope.get("bank_level_validation_forbidden") is True, msg_flag
    forbidden_block = " ".join(cast(list[str], reg.get("forbidden_use", []))).lower()
    missing = [
        p for p in ("bank-level validated", "real-bank confirmed") if p not in forbidden_block
    ]
    msg_block = (
        f"forbidden_use block missing canonical phrase(s): {missing}; "
        f"observed block contents: {forbidden_block!r}"
    )
    assert not missing, msg_block


def test_no_cross_asset_interbank_overclaim() -> None:
    """No 'cross-asset ... interbank ... (validated|proves|confirms)' affirmatives in strict files."""
    # Strict scan: pattern operates per file
    pattern = re.compile(
        r"cross[-\s]asset[\s\S]{0,200}interbank[\s\S]{0,200}(validate[sd]?|prove[sd]?|confirm[sd]?)"
    )
    leaks: list[tuple[str, str]] = []
    for path in _claim_strict_files():
        text_lower = path.read_text(encoding="utf-8").lower()
        for match in pattern.finditer(text_lower):
            snippet = text_lower[max(0, match.start() - 60) : match.end() + 60]
            leaks.append((str(path), snippet))
    msg_leak = (
        f"{len(leaks)} cross-asset/interbank overclaim leak(s) in strict "
        f"(non-declaration) P2 file(s): {leaks[:2]}"
    )
    assert not leaks, msg_leak
    # Distinct second case: registry.json must declare overclaim-forbidden,
    # AND its forbidden_use block MUST list canonical phrases verbatim
    reg = _load_json(REGISTRY_JSON)
    scope = cast(dict[str, Any], reg.get("registry_scope", {}))
    msg_flag = (
        "registry_scope.cross_asset_interbank_overclaim_forbidden must be True; got "
        f"{scope.get('cross_asset_interbank_overclaim_forbidden')!r}"
    )
    assert scope.get("cross_asset_interbank_overclaim_forbidden") is True, msg_flag
    forbidden_block = " ".join(cast(list[str], reg.get("forbidden_use", []))).lower()
    missing = [
        p
        for p in (
            "cross-asset interbank validated",
            "cross-asset interbank proves",
            "cross-asset interbank confirms",
        )
        if p not in forbidden_block
    ]
    msg_block = f"forbidden_use block missing canonical cross-asset/interbank phrase(s): {missing}"
    assert not missing, msg_block


def test_no_ingestion() -> None:
    """No 'ingested' / 'downloaded raw' affirmatives in strict P2 files.

    The artifacts/d002j/ingestion/ directory is P3 territory; once P3
    ships its ingestion *manifest* (contracts only, no bytes ingested),
    the directory legitimately exists. P2's invariant is that strict
    declaration-free files MUST NOT carry ingestion-affirmative phrases,
    NOT that the P3 artifact tree must be absent forever.
    """
    leaks = _scan_strict_for(INGESTION_PATTERNS)
    msg_leak = (
        f"{len(leaks)} ingestion-claim leak(s) in strict (non-declaration) P2 file(s): {leaks[:3]}"
    )
    assert not leaks, msg_leak
    # When P3 ingestion manifest is on disk, the directory holds CONTRACTS
    # ONLY (no staged/ subdirectory with real bytes). The P2 invariant
    # remains: no actual data files under staged/.
    ingest_dir = REPO_ROOT / "artifacts" / "d002j" / "ingestion"
    staged_dir = ingest_dir / "staged"
    msg_staged = (
        f"artifacts/d002j/ingestion/staged/ must NOT contain bytes-ingested data at "
        f"P2 or P3; observed: {staged_dir.exists()}"
    )
    assert not staged_dir.exists(), msg_staged


def test_no_canonical_run_authorized() -> None:
    """No `canonical_run_authorized: true` affirmative declaration in strict P2 files."""
    affirmative_pattern = re.compile(r"canonical_run_authorized\s*[:=]\s*true", re.IGNORECASE)
    leaks: list[tuple[str, int]] = []
    for path in _claim_strict_files():
        text = path.read_text(encoding="utf-8")
        count = len(affirmative_pattern.findall(text))
        if count:
            leaks.append((str(path), count))
    msg_count = (
        f"P2 strict (non-declaration) file(s) contain affirmative "
        f"canonical_run_authorized=true: {leaks}; registry-only PR forbids "
        "authorisation. Declaration files (registry JSON / MD) may carry the "
        "phrase inside forbidden_use / claim_boundary blocks only."
    )
    assert not leaks, msg_count
    # Distinct second case: registry_scope must declare canonical_run_authorized=False
    reg = _load_json(REGISTRY_JSON)
    scope = cast(dict[str, Any], reg.get("registry_scope", {}))
    msg_flag = (
        f"registry_scope.canonical_run_authorized must be False; got "
        f"{scope.get('canonical_run_authorized')!r}"
    )
    assert scope.get("canonical_run_authorized") is False, msg_flag


def test_no_d002j_prereg_edit() -> None:
    """D-002J prereg sha256 byte-exact UNCHANGED; companion locked shas also byte-exact."""
    msg_d002j = (
        f"D-002J prereg sha256 drift: got {_sha256_of(D002J_PREREG)}, "
        f"expected {LOCKED_D002J_PREREG_SHA}; the prereg is the P0 anchor "
        "and MUST NOT be touched in any P2 commit"
    )
    assert _sha256_of(D002J_PREREG) == LOCKED_D002J_PREREG_SHA, msg_d002j
    other_pins: tuple[tuple[Path, str, str], ...] = (
        (
            REPO_ROOT / "docs/governance/D002C_CLAIM_LEDGER.yaml",
            LOCKED_D002C_LEDGER_SHA,
            "D-002C ledger",
        ),
        (
            REPO_ROOT / "docs/governance/D002G_PREREGISTRATION.yaml",
            LOCKED_D002G_PREREG_SHA,
            "D-002G prereg",
        ),
        (
            REPO_ROOT / "docs/governance/D002G_ACCEPTANCE_RULES.md",
            LOCKED_D002G_ACCEPTANCE_SHA,
            "D-002G acceptance",
        ),
        (
            REPO_ROOT / "docs/governance/D002H_PREREGISTRATION.yaml",
            LOCKED_D002H_PREREG_SHA,
            "D-002H prereg",
        ),
        (
            REPO_ROOT / "docs/governance/D002I_PREREGISTRATION.yaml",
            LOCKED_D002I_PREREG_SHA,
            "D-002I prereg",
        ),
    )
    drift: list[tuple[str, str, str]] = []
    for path, expected, label in other_pins:
        got = _sha256_of(path)
        if got != expected:
            drift.append((label, got, expected))
    msg_drift = f"{len(drift)} locked governance sha drift(s): {drift}"
    assert not drift, msg_drift


def test_no_research_systemic_risk_source_edit() -> None:
    """P2 must not modify any file under research/systemic_risk/; acceptor forbids the path."""
    acceptor_text = ACCEPTOR_YAML.read_text(encoding="utf-8")
    msg_forbidden = (
        "acceptor must list 'research/systemic_risk' in forbidden_paths; "
        f"acceptor at {ACCEPTOR_YAML}"
    )
    assert "research/systemic_risk" in acceptor_text, msg_forbidden
    # Distinct second case: the acceptor changed_files whitelist must NOT include
    # any research/systemic_risk path
    bad_lines = [
        line
        for line in acceptor_text.splitlines()
        if "research/systemic_risk" in line and "forbidden" not in line.lower()
    ]
    # Re-scan: only legal occurrence is in forbidden_paths section. We accept
    # the line if it sits inside forbidden_paths (preceding `forbidden_paths:`
    # block in the YAML). Count occurrences in changed_files block.
    in_changed = False
    changed_files_with_research: list[str] = []
    for line in acceptor_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("changed_files:"):
            in_changed = True
            continue
        if stripped.startswith("forbidden_paths:"):
            in_changed = False
            continue
        if stripped and not line.startswith(" ") and not line.startswith("-"):
            in_changed = False
        if in_changed and "research/systemic_risk" in line:
            changed_files_with_research.append(line)
    msg_changed = (
        f"acceptor changed_files contains research/systemic_risk path(s): "
        f"{changed_files_with_research}; forbidden in P2"
    )
    assert not changed_files_with_research, msg_changed
    # NOTE: we cannot diff against origin/main from inside pytest without git
    # access; the acceptor's forbidden_paths is the structural guard. The
    # supplementary check `bad_lines` is informational and not asserted as
    # a hard fail because legal occurrences sit in forbidden_paths.
    _ = bad_lines


def test_blockers_append_only_p2_section() -> None:
    """BLOCKERS.md must end with a 'D-002J-P2' section; previous sections preserved (no rewrite)."""
    text = BLOCKERS_MD.read_text(encoding="utf-8")
    msg_section = (
        "BLOCKERS.md must contain a 'D-002J-P2' header in append-only fashion; "
        "search string 'D-002J-P2' not found"
    )
    assert "D-002J-P2" in text, msg_section
    # Distinct second case: prior P1B section must remain byte-present
    msg_p1b = "BLOCKERS.md must still contain the prior 'D-002J-P1B' section header"
    assert "D-002J-P1B" in text, msg_p1b
    # The P2 section header MUST appear AFTER the P1B section header (append-only).
    # We compare last-occurrence indices because earlier sections may
    # forward-reference P2 ("next legal PR: D-002J-P2") and the P1A
    # section may back-reference P1B.
    p1b_idx = text.rindex("D-002J-P1B")
    p2_idx = text.rindex("D-002J-P2")
    msg_order = (
        f"D-002J-P2 section must appear AFTER D-002J-P1B section in BLOCKERS.md; "
        f"P1B rindex={p1b_idx}, P2 rindex={p2_idx}"
    )
    assert p2_idx > p1b_idx, msg_order


def test_no_unresolved_merge_markers() -> None:
    """No merge-conflict markers in any P2 artifact (regression sentinel)."""
    # Each marker pattern uses string concatenation to avoid the test
    # file itself containing a literal conflict marker that triggers
    # the repo-wide governance guard.
    markers: tuple[str, ...] = (
        "<<<<" + "<<<",
        ">>>>" + ">>>",
        "====" + "===",
    )
    bad_files: list[tuple[str, str]] = []
    for path in (REGISTRY_JSON, SUMMARY_JSON, REGISTRY_MD, RATIONALE_MD, ACCEPTOR_YAML):
        text = path.read_text(encoding="utf-8")
        for m in markers:
            if m in text:
                bad_files.append((str(path), m))
    msg_files = (
        f"{len(bad_files)} merge-marker occurrence(s) in P2 artifacts: {bad_files}; "
        "governance sentinel for tests/governance/test_no_unresolved_merge_markers.py"
    )
    assert not bad_files, msg_files
    # Distinct second case: BLOCKERS append must also be clean
    blockers = BLOCKERS_MD.read_text(encoding="utf-8")
    blockers_markers = [m for m in markers if m in blockers]
    msg_blockers = (
        f"BLOCKERS.md contains merge marker(s): {blockers_markers}; append-only discipline violated"
    )
    assert not blockers_markers, msg_blockers
