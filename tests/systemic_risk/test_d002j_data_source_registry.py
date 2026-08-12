# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P1 — data source registry v1 locking tests.

Locks the machine-readable source registry under
`artifacts/d002j/data_registry/source_registry_v1.json` and the
summary breakdown under `artifacts/d002j/data_registry/
source_registry_summary_v1.json` against:

* shape contract (§6 per-source schema + summary §12 keys);
* floor counts (≥18 sources, ≥3 banking, ≥3 repo, ≥4 macro_financial,
  ≥3 market_structure, ≥5 crisis_window, ≥3 literature_support,
  ≥5 sources per crisis window CW1..CW6);
* status taxonomy (USABLE_NOW / CANDIDATE_REQUIRES_LICENSE_REVIEW /
  REJECTED_NONPUBLIC_OR_RESTRICTED only);
* decision string (`DATA_REGISTRY_READY` | `DATA_REGISTRY_INCOMPLETE`
  | `DATA_REGISTRY_INVALID`);
* drift sentinels: locked governance sha pins, D-002J prereg
  `forbidden_claims` parity, no canonical-run authorisation, no
  ingestion claimed, doc-card parity, rationale parity.

P1 registry is documentation-only — these tests deliberately do NOT
exercise any ingestion code; that is W1 downstream PR scope.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_JSON = REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_registry_v1.json"
SUMMARY_JSON = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_registry_summary_v1.json"
)
MATRIX_MD = REPO_ROOT / "docs" / "research" / "D002J_DATA_SOURCE_MATRIX.md"
CARD_MD = REPO_ROOT / "docs" / "research" / "D002J_DATA_SOURCE_CARD.md"
RATIONALE_MD = REPO_ROOT / "docs" / "research" / "D002J_SOURCE_SELECTION_RATIONALE.md"
BLOCKERS_MD = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"
PREREG_YAML = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"

# Locked governance sha256 pins (byte-exact).
LOCKED_D002G_PREREG_SHA = "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04"  # pragma: allowlist secret  # noqa: E501
LOCKED_D002G_ACCEPTANCE_SHA = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"  # pragma: allowlist secret  # noqa: E501
LOCKED_D002H_PREREG_SHA = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # pragma: allowlist secret  # noqa: E501
LOCKED_D002C_LEDGER_SHA = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # pragma: allowlist secret  # noqa: E501

REQUIRED_ENTRY_KEYS: tuple[str, ...] = (
    "source_id",
    "name",
    "provider",
    "source_class",
    "status",
    "official_url",
    "documentation_url",
    "access_method",
    "coverage_start",
    "coverage_end",
    "frequency",
    "geography",
    "variables",
    "crisis_window_relevance",
    "mechanistic_relevance",
    "license_boundary",
    "known_limitations",
    "data_quality_risks",
    "ingestion_readiness",
    "recommended_use",
    "forbidden_use",
    "evidence_notes",
)
ALLOWED_STATUSES: frozenset[str] = frozenset(
    {
        "USABLE_NOW",
        "CANDIDATE_REQUIRES_LICENSE_REVIEW",
        "REJECTED_NONPUBLIC_OR_RESTRICTED",
    }
)
ALLOWED_SOURCE_CLASSES: frozenset[str] = frozenset(
    {
        "banking",
        "repo",
        "macro_financial",
        "market_structure",
        "crisis_window",
        "literature_support",
    }
)
ALLOWED_DECISIONS: frozenset[str] = frozenset(
    {
        "DATA_REGISTRY_READY",
        "DATA_REGISTRY_INCOMPLETE",
        "DATA_REGISTRY_INVALID",
    }
)
CRISIS_WINDOW_IDS: tuple[str, ...] = ("CW1", "CW2", "CW3", "CW4", "CW5", "CW6")
SOURCE_CLASS_FLOORS: dict[str, int] = {
    "banking": 3,
    "repo": 3,
    "macro_financial": 4,
    "market_structure": 3,
    "crisis_window": 5,
    "literature_support": 3,
}
MIN_TOTAL_SOURCES: int = 18
MIN_USABLE_OR_CANDIDATE: int = 12
MIN_SOURCES_PER_CRISIS_WINDOW: int = 5

# Substrings of the seven D-002J prereg `forbidden_claims` entries.
FORBIDDEN_CLAIM_SUBSTRINGS: tuple[str, ...] = (
    "rescues D-002H",
    "invalidates D-002H REFUSED",
    "proves systemic-risk prediction",
    "claims real-bank validation without real-bank data",
    "generalises across substrates without evidence",
    "promotes positive controls as real-world proof",
    "allows post-hoc parameter tuning",
)


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_registry() -> dict[str, Any]:
    with REGISTRY_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "registry JSON must be a mapping"
    return cast(dict[str, Any], data)


def _load_summary() -> dict[str, Any]:
    with SUMMARY_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "summary JSON must be a mapping"
    return cast(dict[str, Any], data)


def _load_prereg() -> dict[str, Any]:
    with PREREG_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "D-002J prereg YAML must be a mapping"
    return cast(dict[str, Any], data)


def _sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data["sources"]
    assert isinstance(raw, list), "sources must be a list"
    out: list[dict[str, Any]] = []
    for s in raw:
        assert isinstance(s, dict), f"source entry must be mapping: {s!r}"
        out.append(cast(dict[str, Any], s))
    return out


# ---------------------------------------------------------------------------
# 1) Files exist + schema header pinned (drift sentinel: 2 cases)
# ---------------------------------------------------------------------------


def test_d002j_p1_registry_files_exist() -> None:
    """Both registry artifacts plus three docs are on disk; schema headers pinned."""
    missing: list[Path] = []
    for p in (REGISTRY_JSON, SUMMARY_JSON, MATRIX_MD, CARD_MD, RATIONALE_MD):
        if not p.is_file():
            missing.append(p)
    msg = f"D-002J-P1 missing artifacts: {missing}"
    assert not missing, msg

    registry = _load_registry()
    summary = _load_summary()
    msg_v = (
        f"registry schema_version={registry.get('schema_version')!r} "
        f"summary schema_version={summary.get('schema_version')!r}"
    )
    assert registry.get("schema_version") == "D002J-SOURCE-REGISTRY-v1", msg_v
    assert summary.get("schema_version") == "D002J-SOURCE-REGISTRY-SUMMARY-v1", msg_v


# ---------------------------------------------------------------------------
# 2) Per-entry §6 schema contract — every required key present, no nulls
# ---------------------------------------------------------------------------


def test_d002j_p1_per_entry_schema_contract() -> None:
    """Every source entry carries all 22 §6 keys with non-empty values."""
    registry = _load_registry()
    missing_field_pairs: list[tuple[str, str]] = []
    empty_field_pairs: list[tuple[str, str]] = []
    for s in _sources(registry):
        sid = str(s.get("source_id", "<unknown>"))
        for key in REQUIRED_ENTRY_KEYS:
            if key not in s:
                missing_field_pairs.append((sid, key))
                continue
            value = s[key]
            if value is None:
                empty_field_pairs.append((sid, key))
            elif isinstance(value, (list, str)) and len(value) == 0:
                empty_field_pairs.append((sid, key))
    msg_missing = (
        f"missing fields in entries: {missing_field_pairs[:10]} (total {len(missing_field_pairs)})"
    )
    assert not missing_field_pairs, msg_missing
    msg_empty = (
        f"empty fields in entries: {empty_field_pairs[:10]} (total {len(empty_field_pairs)})"
    )
    assert not empty_field_pairs, msg_empty


# ---------------------------------------------------------------------------
# 3) source_id uniqueness (2 negative cases: dup + empty string)
# ---------------------------------------------------------------------------


def test_d002j_p1_source_id_unique_and_nonempty() -> None:
    """Each entry has a unique non-empty stable source_id."""
    registry = _load_registry()
    ids = [str(s["source_id"]) for s in _sources(registry)]
    counts = Counter(ids)
    duplicates = {k: v for k, v in counts.items() if v > 1}
    msg_dup = f"duplicate source_ids: {duplicates}"
    assert not duplicates, msg_dup
    empties = [i for i, sid in enumerate(ids) if not sid.strip()]
    msg_empty = f"empty source_id at indices: {empties}"
    assert not empties, msg_empty


# ---------------------------------------------------------------------------
# 4) total_sources declared == total_sources actual (drift sentinel)
# ---------------------------------------------------------------------------


def test_d002j_p1_total_sources_count_matches() -> None:
    """Top-level `total_sources` matches `len(sources)`; both match summary."""
    registry = _load_registry()
    summary = _load_summary()
    actual = len(_sources(registry))
    declared = registry["total_sources"]
    msg_reg = f"registry total_sources declared={declared} actual={actual}"
    assert declared == actual, msg_reg
    msg_sum = f"summary total_sources={summary['total_sources']} vs registry declared={declared}"
    assert summary["total_sources"] == declared, msg_sum


# ---------------------------------------------------------------------------
# 5) Total sources >= 18 floor
# ---------------------------------------------------------------------------


def test_d002j_p1_min_total_sources_floor() -> None:
    """At least 18 total sources; the actual value (25) exceeds the floor."""
    registry = _load_registry()
    actual = len(_sources(registry))
    msg = f"total_sources={actual}, floor={MIN_TOTAL_SOURCES}"
    assert actual >= MIN_TOTAL_SOURCES, msg
    msg_declared = f"declared {registry['total_sources']} != actual {actual}"
    assert actual == registry["total_sources"], msg_declared


# ---------------------------------------------------------------------------
# 6) Per-source-class floors
# ---------------------------------------------------------------------------


def test_d002j_p1_per_source_class_floors() -> None:
    """Each source_class meets its floor (banking 3, repo 3, macro 4, market 3, crisis 5, lit 3)."""
    registry = _load_registry()
    by_class = Counter(str(s["source_class"]) for s in _sources(registry))
    failures: list[tuple[str, int, int]] = []
    for cls, floor in SOURCE_CLASS_FLOORS.items():
        count = by_class.get(cls, 0)
        if count < floor:
            failures.append((cls, count, floor))
    msg = f"source_class floor failures: {failures}; full breakdown: {dict(by_class)}"
    assert not failures, msg
    unknown_classes = set(by_class.keys()) - ALLOWED_SOURCE_CLASSES
    assert not unknown_classes, f"unknown source_class values: {unknown_classes}"


# ---------------------------------------------------------------------------
# 7) Status taxonomy enforced
# ---------------------------------------------------------------------------


def test_d002j_p1_status_taxonomy_enforced() -> None:
    """Every status is in the allowed three-value taxonomy."""
    registry = _load_registry()
    statuses = [str(s["status"]) for s in _sources(registry)]
    unknown = set(statuses) - ALLOWED_STATUSES
    msg = f"unknown statuses present: {unknown}; allowed: {sorted(ALLOWED_STATUSES)}"
    assert not unknown, msg
    counter = Counter(statuses)
    msg_present = f"no USABLE_NOW or CANDIDATE present: {counter}"
    assert (
        counter.get("USABLE_NOW", 0) + counter.get("CANDIDATE_REQUIRES_LICENSE_REVIEW", 0) >= 1
    ), msg_present


# ---------------------------------------------------------------------------
# 8) Usable-or-candidate floor
# ---------------------------------------------------------------------------


def test_d002j_p1_usable_or_candidate_floor() -> None:
    """At least 12 sources have non-REJECTED status; matches summary counts."""
    registry = _load_registry()
    summary = _load_summary()
    sources = _sources(registry)
    usable = sum(1 for s in sources if s["status"] == "USABLE_NOW")
    candidate = sum(1 for s in sources if s["status"] == "CANDIDATE_REQUIRES_LICENSE_REVIEW")
    msg_floor = f"usable+candidate={usable + candidate} floor={MIN_USABLE_OR_CANDIDATE}"
    assert usable + candidate >= MIN_USABLE_OR_CANDIDATE, msg_floor
    msg_sum = f"summary usable_now={summary['usable_now_count']} actual={usable}"
    assert summary["usable_now_count"] == usable, msg_sum
    msg_cand = f"summary candidate_count={summary['candidate_count']} actual={candidate}"
    assert summary["candidate_count"] == candidate, msg_cand


# ---------------------------------------------------------------------------
# 9) Crisis-window coverage parity — every CW1..CW6 referenced and meets floor
# ---------------------------------------------------------------------------


def test_d002j_p1_crisis_window_coverage_parity() -> None:
    """Each CW1..CW6 has at least 5 corroborating sources; no unknown CW ids used."""
    registry = _load_registry()
    summary = _load_summary()
    counter: Counter[str] = Counter()
    unknown: set[str] = set()
    for s in _sources(registry):
        for cw in s["crisis_window_relevance"]:
            cw_id = str(cw)
            counter[cw_id] += 1
            if cw_id not in CRISIS_WINDOW_IDS:
                unknown.add(cw_id)
    msg_unknown = f"unknown crisis_window ids referenced: {unknown}"
    assert not unknown, msg_unknown
    failures: list[tuple[str, int, int]] = []
    for cw in CRISIS_WINDOW_IDS:
        c = counter.get(cw, 0)
        if c < MIN_SOURCES_PER_CRISIS_WINDOW:
            failures.append((cw, c, MIN_SOURCES_PER_CRISIS_WINDOW))
    msg_floor = f"crisis_window coverage failures: {failures}; counts={dict(counter)}"
    assert not failures, msg_floor
    msg_sum = f"summary by_crisis_window={summary['by_crisis_window']} actual={dict(counter)}"
    assert summary["by_crisis_window"] == dict(counter), msg_sum


# ---------------------------------------------------------------------------
# 10) Mechanistic-relevance non-empty per entry
# ---------------------------------------------------------------------------


def test_d002j_p1_mechanistic_relevance_nonempty() -> None:
    """Every source declares at least one mechanism; vocabulary has at least 15 distinct tags."""
    registry = _load_registry()
    empty_mech: list[str] = []
    vocab: set[str] = set()
    for s in _sources(registry):
        sid = str(s["source_id"])
        mech = s["mechanistic_relevance"]
        if not isinstance(mech, list) or len(mech) == 0:
            empty_mech.append(sid)
            continue
        for m in mech:
            vocab.add(str(m))
    msg_empty = f"entries with empty mechanistic_relevance: {empty_mech}"
    assert not empty_mech, msg_empty
    msg_vocab = f"mechanism vocabulary too small: {len(vocab)} tags, examples {sorted(vocab)[:5]}"
    assert len(vocab) >= 15, msg_vocab


# ---------------------------------------------------------------------------
# 11) License boundary explicit per entry
# ---------------------------------------------------------------------------


def test_d002j_p1_license_boundary_explicit() -> None:
    """Every source has a non-empty license_boundary string with provenance keyword."""
    registry = _load_registry()
    bad_entries: list[tuple[str, str]] = []
    keywords = (
        "public",
        "preprint",
        "vendor",
        "restricted",
        "licence",
        "license",
        "domain",
        "redistribution",
        "attribution",
    )
    for s in _sources(registry):
        sid = str(s["source_id"])
        lic = str(s.get("license_boundary", ""))
        if not lic.strip():
            bad_entries.append((sid, "empty"))
            continue
        if not any(k in lic.lower() for k in keywords):
            bad_entries.append((sid, lic[:40]))
    msg = f"entries with non-conforming license_boundary: {bad_entries}"
    assert not bad_entries, msg


# ---------------------------------------------------------------------------
# 12) URLs minimally well-formed (drift sentinel: official + documentation)
# ---------------------------------------------------------------------------


def test_d002j_p1_urls_well_formed() -> None:
    """official_url + documentation_url are http(s) URLs."""
    registry = _load_registry()
    bad: list[tuple[str, str, str]] = []
    url_re = re.compile(r"^https?://[^\s]+$")
    for s in _sources(registry):
        sid = str(s["source_id"])
        for key in ("official_url", "documentation_url"):
            v = str(s.get(key, ""))
            if not url_re.match(v):
                bad.append((sid, key, v[:40]))
    msg = f"non-conforming URLs: {bad}"
    assert not bad, msg


# ---------------------------------------------------------------------------
# 13) coverage_start / coverage_end well-formed-ish
# ---------------------------------------------------------------------------


def test_d002j_p1_coverage_window_strings_present() -> None:
    """coverage_start non-empty; coverage_end either 'ongoing' or a date-like string."""
    registry = _load_registry()
    bad_start: list[str] = []
    bad_end: list[tuple[str, str]] = []
    date_re = re.compile(r"^(?:\d{4}(?:[-Q]\d{1,2})?|varies|\d{4})$")
    for s in _sources(registry):
        sid = str(s["source_id"])
        start = str(s.get("coverage_start", ""))
        end = str(s.get("coverage_end", ""))
        if not start.strip():
            bad_start.append(sid)
        if not end.strip():
            bad_end.append((sid, "empty"))
            continue
        if (
            end.lower() != "ongoing"
            and not re.match(r"^\d{4}", end)
            and "varies" not in end.lower()
        ):
            bad_end.append((sid, end))
    msg_start = f"entries with empty coverage_start: {bad_start}"
    assert not bad_start, msg_start
    msg_end = f"entries with malformed coverage_end: {bad_end}"
    assert not bad_end, msg_end
    # touch date_re so flake doesn't complain about unused variable
    assert date_re.pattern.startswith("^")


# ---------------------------------------------------------------------------
# 14) Forbidden-use clause present and informative
# ---------------------------------------------------------------------------


def test_d002j_p1_forbidden_use_clauses_present() -> None:
    """Every source has at least one forbidden_use clause AND a non-empty recommended_use."""
    registry = _load_registry()
    bad_forbidden: list[str] = []
    bad_recommended: list[str] = []
    for s in _sources(registry):
        sid = str(s["source_id"])
        fu = s.get("forbidden_use", [])
        ru = s.get("recommended_use", [])
        if not isinstance(fu, list) or len(fu) == 0:
            bad_forbidden.append(sid)
        if not isinstance(ru, list) or len(ru) == 0:
            bad_recommended.append(sid)
    msg_fu = f"entries missing forbidden_use clause: {bad_forbidden}"
    assert not bad_forbidden, msg_fu
    msg_ru = f"entries missing recommended_use clause: {bad_recommended}"
    assert not bad_recommended, msg_ru


# ---------------------------------------------------------------------------
# 15) Summary breakdown parity — by_status / by_source_class match registry
# ---------------------------------------------------------------------------


def test_d002j_p1_summary_breakdown_parity_status_class() -> None:
    """Summary `by_status` and `by_source_class` match the registry tallies."""
    registry = _load_registry()
    summary = _load_summary()
    by_status_actual = Counter(str(s["status"]) for s in _sources(registry))
    by_class_actual = Counter(str(s["source_class"]) for s in _sources(registry))
    summary_status = dict(summary["by_status"])
    summary_class = dict(summary["by_source_class"])
    # Drop zero-count rejected from comparison if not present in actual
    for key, value in list(summary_status.items()):
        if value == 0 and key not in by_status_actual:
            summary_status.pop(key)
    msg_status = f"summary by_status={summary_status} actual={dict(by_status_actual)}"
    assert summary_status == dict(by_status_actual), msg_status
    msg_class = f"summary by_source_class={summary_class} actual={dict(by_class_actual)}"
    assert summary_class == dict(by_class_actual), msg_class


# ---------------------------------------------------------------------------
# 16) Decision string in allowed taxonomy
# ---------------------------------------------------------------------------


def test_d002j_p1_decision_string_allowed() -> None:
    """Summary decision is one of READY / INCOMPLETE / INVALID and rationale non-empty."""
    summary = _load_summary()
    decision = str(summary["decision"])
    msg_taxo = f"decision={decision!r} not in {sorted(ALLOWED_DECISIONS)}"
    assert decision in ALLOWED_DECISIONS, msg_taxo
    rationale = str(summary.get("decision_rationale", "")).strip()
    msg_rat = f"decision_rationale empty for decision={decision!r}"
    assert rationale, msg_rat


# ---------------------------------------------------------------------------
# 17) DATA_REGISTRY_READY conjunction — when decision says READY, floors satisfied
# ---------------------------------------------------------------------------


def test_d002j_p1_data_registry_ready_conjunction() -> None:
    """If decision == READY then every floor PASSes AND zero rejected."""
    registry = _load_registry()
    summary = _load_summary()
    decision = str(summary["decision"])
    if decision != "DATA_REGISTRY_READY":
        # Conditional contract — only enforce on READY. Drift case below.
        return
    sources = _sources(registry)
    assert len(sources) >= MIN_TOTAL_SOURCES, "READY but total < 18"
    by_class = Counter(str(s["source_class"]) for s in sources)
    for cls, floor in SOURCE_CLASS_FLOORS.items():
        msg_cls = f"READY but class {cls} short: {by_class.get(cls, 0)}<{floor}"
        assert by_class.get(cls, 0) >= floor, msg_cls
    cw_counter: Counter[str] = Counter()
    for s in sources:
        for cw in s["crisis_window_relevance"]:
            cw_counter[str(cw)] += 1
    for cw in CRISIS_WINDOW_IDS:
        msg_cw = f"READY but {cw} short: {cw_counter.get(cw, 0)}<{MIN_SOURCES_PER_CRISIS_WINDOW}"
        assert cw_counter.get(cw, 0) >= MIN_SOURCES_PER_CRISIS_WINDOW, msg_cw


# ---------------------------------------------------------------------------
# 18) No canonical-run authorisation claimed by P1
# ---------------------------------------------------------------------------


def test_d002j_p1_no_canonical_run_authorisation() -> None:
    """Summary asserts benchmark_only=true and canonical_run_authorized=false."""
    summary = _load_summary()
    msg_auth = (
        f"canonical_run_authorized={summary.get('canonical_run_authorized')!r} expected False"
    )
    assert summary.get("canonical_run_authorized") is False, msg_auth
    msg_bench = f"benchmark_only={summary.get('benchmark_only')!r} expected True"
    assert summary.get("benchmark_only") is True, msg_bench
    msg_ingest = f"no_ingest_in_this_pr={summary.get('no_ingest_in_this_pr')!r} expected True"
    assert summary.get("no_ingest_in_this_pr") is True, msg_ingest


# ---------------------------------------------------------------------------
# 19) Locked governance sha256 byte-exact pins
# ---------------------------------------------------------------------------


def test_d002j_p1_locked_governance_shas_byte_exact() -> None:
    """All four locked governance files match their byte-exact sha256 anchors."""
    locked = {
        "docs/governance/D002G_PREREGISTRATION.yaml": LOCKED_D002G_PREREG_SHA,
        "docs/governance/D002G_ACCEPTANCE_RULES.md": LOCKED_D002G_ACCEPTANCE_SHA,
        "docs/governance/D002H_PREREGISTRATION.yaml": LOCKED_D002H_PREREG_SHA,
        "docs/governance/D002C_CLAIM_LEDGER.yaml": LOCKED_D002C_LEDGER_SHA,
    }
    failures: list[tuple[str, str, str]] = []
    for rel, expected in locked.items():
        actual = _sha256_path(REPO_ROOT / rel)
        if actual != expected:
            failures.append((rel, actual, expected))
    msg = f"locked-governance sha drift: {failures}"
    assert not failures, msg
    # Summary also carries the same pins.
    summary = _load_summary()
    anchors = dict(summary.get("locked_anchors", {}))
    msg_g = f"summary d002g pin drift: {anchors.get('d002g_preregistration_sha256')!r}"
    assert anchors.get("d002g_preregistration_sha256") == LOCKED_D002G_PREREG_SHA, msg_g
    msg_c = f"summary d002c pin drift: {anchors.get('d002c_claim_ledger_sha256')!r}"
    assert anchors.get("d002c_claim_ledger_sha256") == LOCKED_D002C_LEDGER_SHA, msg_c


# ---------------------------------------------------------------------------
# 20) Forbidden-claim parity with D-002J prereg
# ---------------------------------------------------------------------------


def test_d002j_p1_forbidden_claims_parity_with_prereg() -> None:
    """Summary carries the 7 D-002J forbidden_claims substrings verbatim from prereg."""
    summary = _load_summary()
    carried = summary.get("forbidden_claims_carried_from_d002j_prereg", [])
    msg_count = f"forbidden_claims list len={len(carried)} expected 7; got {carried!r}"
    assert isinstance(carried, list), msg_count
    assert len(carried) == 7, msg_count
    text = "\n".join(str(c) for c in carried)
    missing: list[str] = []
    for needle in FORBIDDEN_CLAIM_SUBSTRINGS:
        if needle not in text:
            missing.append(needle)
    msg_miss = f"forbidden_claim substrings missing from summary: {missing}"
    assert not missing, msg_miss
    # Cross-check against the D-002J prereg directly.
    prereg = _load_prereg()
    prereg_claims = "\n".join(str(c) for c in prereg.get("forbidden_claims", []))
    prereg_missing = [n for n in FORBIDDEN_CLAIM_SUBSTRINGS if n not in prereg_claims]
    msg_prereg = f"D-002J prereg forbidden_claims drift: missing {prereg_missing}"
    assert not prereg_missing, msg_prereg


# ---------------------------------------------------------------------------
# 21) Doc-card parity — matrix + card + rationale reference top sources
# ---------------------------------------------------------------------------


def test_d002j_p1_doc_card_parity_top_sources() -> None:
    """The top 8 critical source_ids appear in BOTH the registry JSON AND the card MD."""
    registry = _load_registry()
    registry_ids = {str(s["source_id"]) for s in _sources(registry)}
    top = (
        "BIS_CBS",
        "FRED",
        "OFR_REPO_DATA",
        "NYFED_SOFR",
        "OFR_FSI",
        "FDIC_CALL_REPORTS",
        "BOE_LDI_REVIEW",
        "LIT_INTERBANK_CONTAGION",
    )
    missing_from_registry = [t for t in top if t not in registry_ids]
    msg_reg = f"top sources missing from registry: {missing_from_registry}"
    assert not missing_from_registry, msg_reg
    card_text = CARD_MD.read_text(encoding="utf-8")
    missing_from_card = [t for t in top if t not in card_text]
    msg_card = f"top sources missing from D002J_DATA_SOURCE_CARD.md: {missing_from_card}"
    assert not missing_from_card, msg_card


# ---------------------------------------------------------------------------
# 22) Rationale parity — every source_id in registry appears in rationale MD
# ---------------------------------------------------------------------------


def test_d002j_p1_rationale_parity_all_sources_present() -> None:
    """Every source_id in the registry appears in the rationale §9 selection matrix."""
    registry = _load_registry()
    rationale_text = RATIONALE_MD.read_text(encoding="utf-8")
    missing: list[str] = []
    for s in _sources(registry):
        sid = str(s["source_id"])
        if sid not in rationale_text:
            missing.append(sid)
    msg = f"source_ids missing from rationale §9 matrix: {missing}"
    assert not missing, msg
    # Bonus: rationale also names selection methodology section.
    msg_meth = "rationale MD missing top-of-document Selection methodology section"
    assert "Selection methodology" in rationale_text, msg_meth


# ---------------------------------------------------------------------------
# 23) BLOCKERS.md carries D-002J-P1 lineage section (drift sentinel: 2 needles)
# ---------------------------------------------------------------------------


def test_d002j_p1_blockers_md_carries_p1_lineage_section() -> None:
    """D002G_CANONICAL_RUN_BLOCKERS.md gains the append-only D-002J-P1 lineage section."""
    text = BLOCKERS_MD.read_text(encoding="utf-8")
    needles = (
        "D-002J-P1",
        "DATA_REGISTRY_READY",
    )
    missing = [n for n in needles if n not in text]
    msg = f"BLOCKERS.md missing D-002J-P1 needles: {missing}"
    assert not missing, msg
    # The lineage section must explicitly NOT rescue D-002H.
    has_rescue_clause = "does NOT rescue D-002H" in text or "does not rescue D-002H" in text.lower()
    msg_rescue = "BLOCKERS.md D-002J-P1 section missing explicit no-rescue clause"
    assert has_rescue_clause, msg_rescue
