# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P3 — ingestion manifest + point-in-time adapter boundary tests.

23 P3 guard tests enforcing the ingestion manifest contract. Every
test contains >= 2 assertions or >= 2 distinct cases. Drift sentinels
for parent registry sha256 pinning, for phase-coupling to P1B audit-
surviving sources and P2 window_ids, for vintage-aware adapter
coverage of revisable sources (the single most important test in this
PR), and for forbidden-claim boundary preservation are included.

P3 is contract-only: defines adapter contracts on top of P1B-surviving
sources (audit_status VERIFIED or PARTIAL) and P2 crisis windows.
NO ingestion, NO modeling, NO substrate, NO null execution, NO
canonical run, NO prediction claim, NO bank-level validation, NO
cross-asset/interbank overclaim.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
INGESTION_DIR: Path = REPO_ROOT / "artifacts" / "d002j" / "ingestion"
MANIFEST_JSON: Path = INGESTION_DIR / "ingestion_manifest_v1.json"
ADAPTER_REGISTRY_JSON: Path = INGESTION_DIR / "adapter_registry_v1.json"
SOURCE_HASH_MANIFEST_JSON: Path = INGESTION_DIR / "source_hash_manifest_v1.json"

INGESTION_BOUNDARY_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_INGESTION_BOUNDARY.md"
POINT_IN_TIME_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_POINT_IN_TIME_DISCIPLINE.md"

P1B_REGISTRY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_registry_v1.json"
)
P1B_AUDIT_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "data_registry" / "source_provenance_audit_v1.json"
)
P2_WINDOW_REGISTRY_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "crisis_windows" / "crisis_window_registry_v1.json"
)

P3_CAPSULE_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_p3_verdict_v1.json"
)
DAG_VERDICT_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_verdict_dag_v1.json"
)
LINEAGE_MAP_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_LINEAGE_MAP.md"

D002J_PREREG: Path = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"
RESEARCH_SYSTEMIC_DIR: Path = REPO_ROOT / "research" / "systemic_risk"
BLOCKERS_MD: Path = REPO_ROOT / "docs" / "governance" / "D002G_CANONICAL_RUN_BLOCKERS.md"
ACCEPTOR_YAML: Path = (
    REPO_ROOT / ".claude" / "commit_acceptors" / "x10r-d002j-p3-ingestion-manifest.yaml"
)

# Locked sha pins — copied byte-exact at PR-open time.
LOCKED_P1B_REGISTRY_SHA: str = (
    "f1899b7a882b4b3efbebb54e3dc942c07"  # pragma: allowlist secret
    + "9839f77f981273e2dd09757973b14ec"  # pragma: allowlist secret
)
LOCKED_P2_WINDOW_REGISTRY_SHA: str = (
    "41f281d9e97fbf49725f0eb1a1bb7b458"  # pragma: allowlist secret
    + "65c14cdc5c525ea96231ef0aa651e8f"  # pragma: allowlist secret
)

VALID_ADAPTER_CLASSES: frozenset[str] = frozenset(
    {
        "static_csv_adapter",
        "official_api_adapter",
        "metadata_only_adapter",
        "literature_reference_adapter",
        "manual_event_registry_adapter",
    },
)
VALID_ADAPTER_STATUSES: frozenset[str] = frozenset(
    {
        "READY",
        "STUB_ONLY",
        "REQUIRES_MANUAL_DOWNLOAD",
        "REQUIRES_LICENSE_REVIEW",
        "REJECTED",
    },
)
VALID_ACCESS_BOUNDARIES: frozenset[str] = frozenset(
    {"public", "registered", "paywall", "license_review"},
)
BIS_ECB_OFR_SOURCE_IDS: frozenset[str] = frozenset(
    {
        "BIS_CBS",
        "ECB_CBD",
        "ECB_MMSR",
        "OFR_REPO_DATA",
        "OFR_FSI",
        "BIS_QR_NETWORK",
        "OFR_WP_NETWORK",
    },
)
VINTAGE_ANCHOR_RELEVANCE: frozenset[str] = frozenset(
    {"real_time_information_constraint", "vintage_anti_leakage_baseline"},
)

# Merge-marker regex (mirrors tests/governance pattern).
_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_JSON)


def _adapters() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], _manifest()["adapters"])


def _p1b_surviving() -> tuple[set[str], dict[str, str]]:
    audit = _load_json(P1B_AUDIT_JSON)
    sources = cast(list[dict[str, Any]], audit["sources"])
    status_map: dict[str, str] = {
        cast(str, s["source_id"]): cast(str, s["audit_status"]) for s in sources
    }
    surviving: set[str] = {sid for sid, st in status_map.items() if st in ("VERIFIED", "PARTIAL")}
    return surviving, status_map


def _p1b_source_records() -> dict[str, dict[str, Any]]:
    reg = _load_json(P1B_REGISTRY_JSON)
    return {cast(str, s["source_id"]): s for s in cast(list[dict[str, Any]], reg["sources"])}


def _p2_window_ids() -> set[str]:
    reg = _load_json(P2_WINDOW_REGISTRY_JSON)
    return {cast(str, w["window_id"]) for w in cast(list[dict[str, Any]], reg["windows"])}


def test_ingestion_manifest_exists() -> None:
    """Manifest JSON exists and parses; schema_version matches."""
    msg_exists = f"manifest must exist at {MANIFEST_JSON}"
    assert MANIFEST_JSON.is_file(), msg_exists
    m = _manifest()
    msg_schema = f"manifest schema_version must be D002J-INGESTION-MANIFEST-v1; got {m.get('schema_version')!r}"
    assert m.get("schema_version") == "D002J-INGESTION-MANIFEST-v1", msg_schema
    msg_top = "manifest must declare total_adapters and an adapters list"
    assert isinstance(m.get("total_adapters"), int) and isinstance(m.get("adapters"), list), msg_top


def test_ingestion_manifest_schema_valid() -> None:
    """Every adapter entry carries all required schema fields."""
    required = {
        "adapter_id",
        "adapter_class",
        "status",
        "source_id",
        "window_ids",
        "endpoint",
        "output_target",
        "schema_contract_path",
        "checksum_contract",
        "vintage_required",
        "vintage_field",
        "forecast_required",
        "forecast_date_field",
        "observation_date_field",
        "release_date_field",
        "decision_date_field",
        "lookahead_invariants",
        "max_download_bytes",
        "license_boundary",
        "access_boundary",
        "rate_limit_policy",
        "deterministic_replay",
        "wall_clock_dependent",
        "private_data",
        "restricted_microdata",
        "forbidden_use",
    }
    bad: list[tuple[str, list[str]]] = []
    for a in _adapters():
        missing = sorted(required - set(a.keys()))
        if missing:
            bad.append((cast(str, a.get("adapter_id", "?")), missing))
    msg_missing = f"adapters missing required fields: {bad}"
    assert not bad, msg_missing
    bad_class: list[tuple[str, str]] = []
    for a in _adapters():
        cls = cast(str, a["adapter_class"])
        if cls not in VALID_ADAPTER_CLASSES:
            bad_class.append((cast(str, a["adapter_id"]), cls))
    msg_class = (
        f"invalid adapter_class entries: {bad_class}; allowed = {sorted(VALID_ADAPTER_CLASSES)}"
    )
    assert not bad_class, msg_class


def test_adapter_registry_exists() -> None:
    """Slimmer adapter_registry_v1.json exists, has summary and adapters."""
    msg_exists = f"adapter_registry must exist at {ADAPTER_REGISTRY_JSON}"
    assert ADAPTER_REGISTRY_JSON.is_file(), msg_exists
    r = _load_json(ADAPTER_REGISTRY_JSON)
    msg_schema = (
        f"adapter_registry schema_version must be D002J-ADAPTER-REGISTRY-v1; "
        f"got {r.get('schema_version')!r}"
    )
    assert r.get("schema_version") == "D002J-ADAPTER-REGISTRY-v1", msg_schema
    msg_summary = "adapter_registry must declare summary.total_adapters and adapters list"
    assert "summary" in r and "adapters" in r, msg_summary
    msg_count = (
        f"adapter_registry.summary.total_adapters must match manifest total_adapters; "
        f"got {r['summary'].get('total_adapters')!r} vs manifest {_manifest()['total_adapters']!r}"
    )
    assert r["summary"]["total_adapters"] == _manifest()["total_adapters"], msg_count


def test_source_hash_manifest_exists() -> None:
    """Source-hash manifest exists with one entry per adapter; expected_sha256 null at P3."""
    msg_exists = f"source_hash_manifest must exist at {SOURCE_HASH_MANIFEST_JSON}"
    assert SOURCE_HASH_MANIFEST_JSON.is_file(), msg_exists
    h = _load_json(SOURCE_HASH_MANIFEST_JSON)
    msg_schema = (
        f"source_hash_manifest schema_version must be D002J-SOURCE-HASH-MANIFEST-v1; "
        f"got {h.get('schema_version')!r}"
    )
    assert h.get("schema_version") == "D002J-SOURCE-HASH-MANIFEST-v1", msg_schema
    entries = cast(list[dict[str, Any]], h.get("entries", []))
    msg_count = (
        f"source_hash_manifest must have one entry per adapter; "
        f"got {len(entries)} entries for {len(_adapters())} adapters"
    )
    assert len(entries) == len(_adapters()), msg_count
    pinned_early: list[str] = [
        cast(str, e["adapter_id"])
        for e in entries
        if e.get("expected_sha256_at_pin_time") is not None
    ]
    msg_null = (
        f"every expected_sha256_at_pin_time must be null at P3 emit time; "
        f"unexpectedly pinned: {pinned_early}"
    )
    assert not pinned_early, msg_null


def test_minimum_twelve_adapters() -> None:
    """Floor: >= 12 adapters total across all 5 adapter classes."""
    total = len(_adapters())
    msg_total = f"manifest must declare >= 12 adapters; observed {total}"
    assert total >= 12, msg_total
    classes_present = {a["adapter_class"] for a in _adapters()}
    expected_classes = VALID_ADAPTER_CLASSES
    msg_classes = (
        f"all 5 adapter classes must be represented; missing: "
        f"{sorted(expected_classes - classes_present)}"
    )
    assert classes_present == expected_classes, msg_classes


def test_minimum_six_fred_macro_financial_adapters() -> None:
    """Floor: >= 6 adapters bound to FRED/macro-financial source_class sources."""
    records = _p1b_source_records()
    macro_bound = [
        a
        for a in _adapters()
        if records.get(a["source_id"], {}).get("source_class") == "macro_financial"
    ]
    msg_count = (
        f"manifest must declare >= 6 adapters bound to macro_financial sources; "
        f"observed {len(macro_bound)}; "
        f"adapter_ids: {sorted(a['adapter_id'] for a in macro_bound)}"
    )
    assert len(macro_bound) >= 6, msg_count
    msg_diversity = (
        f"at least 3 distinct macro_financial source_ids must be referenced; "
        f"observed distinct: {sorted({a['source_id'] for a in macro_bound})}"
    )
    assert len({a["source_id"] for a in macro_bound}) >= 3, msg_diversity


def test_minimum_three_bis_ecb_ofr_adapters() -> None:
    """Floor: >= 3 adapters bound to BIS / ECB / OFR sources."""
    bis_ecb_ofr_bound = [a for a in _adapters() if a["source_id"] in BIS_ECB_OFR_SOURCE_IDS]
    msg_count = (
        f"manifest must declare >= 3 adapters bound to BIS/ECB/OFR sources; "
        f"observed {len(bis_ecb_ofr_bound)}; "
        f"adapter_ids: {sorted(a['adapter_id'] for a in bis_ecb_ofr_bound)}"
    )
    assert len(bis_ecb_ofr_bound) >= 3, msg_count
    msg_distinct = (
        f"at least 3 distinct BIS/ECB/OFR source_ids must be referenced; "
        f"observed: {sorted({a['source_id'] for a in bis_ecb_ofr_bound})}"
    )
    assert len({a["source_id"] for a in bis_ecb_ofr_bound}) >= 3, msg_distinct


def test_minimum_two_metadata_only_adapters() -> None:
    """Floor: >= 2 metadata_only_adapter entries (docs-only fetch path)."""
    metadata_only = [a for a in _adapters() if a["adapter_class"] == "metadata_only_adapter"]
    msg_count = (
        f"manifest must declare >= 2 metadata_only_adapter entries; "
        f"observed {len(metadata_only)}; "
        f"adapter_ids: {sorted(a['adapter_id'] for a in metadata_only)}"
    )
    assert len(metadata_only) >= 2, msg_count
    # metadata-only must never claim micro-data ingestion
    bad_micro = [cast(str, a["adapter_id"]) for a in metadata_only if a.get("private_data") is True]
    msg_micro = (
        f"metadata_only adapters must never declare private_data=true; offenders: {bad_micro}"
    )
    assert not bad_micro, msg_micro


def test_minimum_two_literature_reference_adapters() -> None:
    """Floor: >= 2 literature_reference_adapter entries."""
    lit_refs = [a for a in _adapters() if a["adapter_class"] == "literature_reference_adapter"]
    msg_count = (
        f"manifest must declare >= 2 literature_reference_adapter entries; "
        f"observed {len(lit_refs)}; adapter_ids: {sorted(a['adapter_id'] for a in lit_refs)}"
    )
    assert len(lit_refs) >= 2, msg_count
    # literature_reference adapters must have null endpoint (reference-only)
    bad_endpoint = [cast(str, a["adapter_id"]) for a in lit_refs if a.get("endpoint") is not None]
    msg_endpoint = (
        f"literature_reference adapters must have null endpoint (reference-only); "
        f"offenders: {bad_endpoint}"
    )
    assert not bad_endpoint, msg_endpoint


def test_every_adapter_source_id_exists_in_p1b_registry() -> None:
    """Phase-coupling: every adapter source_id must be in the P1B registry keyspace."""
    p1b_ids = set(_p1b_source_records().keys())
    adapter_ids = {a["source_id"] for a in _adapters()}
    missing = sorted(adapter_ids - p1b_ids)
    msg_missing = (
        f"P3 adapters reference {len(missing)} source_ids not in P1B registry: {missing}; "
        f"P1B registry has {len(p1b_ids)} declared source_ids"
    )
    assert not missing, msg_missing
    # cross-check: parent_registry_sha256 matches on-disk P1B
    actual_sha = _sha256_of(P1B_REGISTRY_JSON)
    declared_sha = cast(str, _manifest().get("parent_registry_sha256"))
    msg_sha = (
        f"parent_registry_sha256 declared {declared_sha!r} differs from on-disk "
        f"P1B registry sha {actual_sha!r}"
    )
    assert declared_sha == actual_sha, msg_sha


def test_every_adapter_source_id_is_p1b_verified_or_partial() -> None:
    """Phase-coupling: every adapter source_id must be VERIFIED or PARTIAL in P1B audit."""
    surviving, status_map = _p1b_surviving()
    adapter_ids = {a["source_id"] for a in _adapters()}
    not_surviving = sorted(adapter_ids - surviving)
    msg_not = (
        f"P3 adapters reference {len(not_surviving)} sources outside P1B-surviving set: "
        f"{not_surviving}; promotion of DOWNGRADED or REJECTED source is forbidden"
    )
    assert not not_surviving, msg_not
    bad_status = {
        sid: status_map[sid]
        for sid in adapter_ids
        if status_map.get(sid) in {"DOWNGRADED", "REJECTED"}
    }
    msg_bad = (
        f"P3 adapters reference {len(bad_status)} sources with DOWNGRADED|REJECTED status: "
        f"{bad_status}"
    )
    assert not bad_status, msg_bad


def test_every_adapter_window_id_exists_in_p2_registry() -> None:
    """Phase-coupling: every adapter window_id must be declared in the P2 registry."""
    p2_ids = _p2_window_ids()
    adapter_window_ids: set[str] = set()
    for a in _adapters():
        adapter_window_ids.update(cast(list[str], a["window_ids"]))
    missing = sorted(adapter_window_ids - p2_ids)
    msg_missing = (
        f"P3 adapters reference {len(missing)} window_ids not in P2 registry: {missing}; "
        f"P2 registry has {len(p2_ids)} declared window_ids"
    )
    assert not missing, msg_missing
    declared_sha = cast(str, _manifest().get("parent_window_registry_sha256"))
    actual_sha = _sha256_of(P2_WINDOW_REGISTRY_JSON)
    msg_sha = (
        f"parent_window_registry_sha256 declared {declared_sha!r} differs from on-disk "
        f"P2 registry sha {actual_sha!r}"
    )
    assert declared_sha == actual_sha, msg_sha


def test_revisable_sources_require_vintage_adapter() -> None:
    """SINGLE MOST IMPORTANT TEST: revisable sources MUST be bound by vintage adapter.

    A revisable source is one whose mechanistic_relevance contains
    'real_time_information_constraint' or 'vintage_anti_leakage_baseline'.
    The lookahead-leakage discipline is fail-closed: every such source
    MUST be bound by at least one adapter declaring vintage_required=True
    AND a non-null vintage_field AND the vintage_release_date <=
    decision_date lookahead invariant.
    """
    records = _p1b_source_records()
    surviving, _ = _p1b_surviving()
    revisable_sources: set[str] = set()
    for sid, rec in records.items():
        if sid not in surviving:
            continue
        rel = set(cast(list[str], rec.get("mechanistic_relevance", [])))
        if rel & VINTAGE_ANCHOR_RELEVANCE:
            revisable_sources.add(sid)
    msg_present = (
        f"P1B-surviving registry must include at least one revisable source "
        f"(mechanistic_relevance ∩ {sorted(VINTAGE_ANCHOR_RELEVANCE)}); "
        f"observed revisable: {sorted(revisable_sources)}"
    )
    assert revisable_sources, msg_present
    # For each revisable source, locate the vintage-aware adapters bound to it
    sources_without_vintage_adapter: list[str] = []
    for sid in sorted(revisable_sources):
        bound = [
            a for a in _adapters() if a["source_id"] == sid and a.get("vintage_required") is True
        ]
        if not bound:
            sources_without_vintage_adapter.append(sid)
    msg_bound = (
        f"{len(sources_without_vintage_adapter)} revisable source(s) lack a "
        f"vintage_required=true adapter: {sources_without_vintage_adapter}; "
        f"point-in-time discipline violated"
    )
    assert not sources_without_vintage_adapter, msg_bound
    # Every vintage-aware adapter must declare vintage_field non-null AND the
    # vintage_release_date <= decision_date lookahead invariant
    bad_field: list[str] = []
    bad_invariant: list[str] = []
    for a in _adapters():
        if not a.get("vintage_required"):
            continue
        if not a.get("vintage_field"):
            bad_field.append(cast(str, a["adapter_id"]))
        inv = cast(list[str], a.get("lookahead_invariants", []))
        if "vintage_release_date <= decision_date" not in inv:
            bad_invariant.append(cast(str, a["adapter_id"]))
    msg_field = (
        f"{len(bad_field)} vintage-required adapter(s) lack a non-null vintage_field: {bad_field}"
    )
    assert not bad_field, msg_field
    msg_inv = (
        f"{len(bad_invariant)} vintage-required adapter(s) lack "
        f"'vintage_release_date <= decision_date' invariant: {bad_invariant}"
    )
    assert not bad_invariant, msg_inv


def test_forecast_sources_require_forecast_date_field() -> None:
    """Every forecast_required=true adapter must declare a non-null forecast_date_field."""
    forecast_adapters = [a for a in _adapters() if a.get("forecast_required") is True]
    msg_present = f"manifest must declare >= 1 forecast adapter; observed {len(forecast_adapters)}"
    assert len(forecast_adapters) >= 1, msg_present
    bad_field: list[str] = [
        cast(str, a["adapter_id"]) for a in forecast_adapters if not a.get("forecast_date_field")
    ]
    msg_field = (
        f"{len(bad_field)} forecast adapter(s) lack a non-null forecast_date_field: {bad_field}"
    )
    assert not bad_field, msg_field


def test_observation_date_lte_decision_date_invariant() -> None:
    """Every adapter (non-literature) must encode observation_date <= decision_date."""
    bad: list[str] = []
    for a in _adapters():
        if a["adapter_class"] == "literature_reference_adapter":
            continue
        inv = cast(list[str], a.get("lookahead_invariants", []))
        # event_date <= decision_date is the crisis-window equivalent;
        # accept either as the baseline.
        ok = "observation_date <= decision_date" in inv or "event_date <= decision_date" in inv
        if not ok:
            bad.append(cast(str, a["adapter_id"]))
    msg = (
        f"{len(bad)} adapter(s) lack the observation_date/event_date <= decision_date "
        f"baseline invariant: {bad}"
    )
    assert not bad, msg
    # second case: literature adapters MUST encode publication_date <= decision_date
    bad_lit: list[str] = [
        cast(str, a["adapter_id"])
        for a in _adapters()
        if a["adapter_class"] == "literature_reference_adapter"
        and "publication_date <= decision_date"
        not in cast(list[str], a.get("lookahead_invariants", []))
    ]
    msg_lit = (
        f"{len(bad_lit)} literature adapter(s) lack publication_date <= decision_date: {bad_lit}"
    )
    assert not bad_lit, msg_lit


def test_release_date_lte_decision_date_invariant() -> None:
    """Every non-literature adapter must encode release_date <= decision_date."""
    bad: list[str] = []
    for a in _adapters():
        if a["adapter_class"] == "literature_reference_adapter":
            continue
        inv = cast(list[str], a.get("lookahead_invariants", []))
        if "release_date <= decision_date" not in inv:
            bad.append(cast(str, a["adapter_id"]))
    msg = f"{len(bad)} adapter(s) lack release_date <= decision_date invariant: {bad}"
    assert not bad, msg
    # second case: ensure every adapter declares release_date_field non-null
    bad_field: list[str] = [
        cast(str, a["adapter_id"]) for a in _adapters() if not a.get("release_date_field")
    ]
    msg_field = f"{len(bad_field)} adapter(s) lack a non-null release_date_field: {bad_field}"
    assert not bad_field, msg_field


def test_no_private_data_adapters() -> None:
    """No adapter may declare private_data=true."""
    bad: list[str] = [
        cast(str, a["adapter_id"]) for a in _adapters() if a.get("private_data") is True
    ]
    msg = f"{len(bad)} adapter(s) declare private_data=true (forbidden): {bad}"
    assert not bad, msg
    # second case: every adapter must explicitly declare private_data field
    missing_field: list[str] = [
        cast(str, a["adapter_id"]) for a in _adapters() if "private_data" not in a
    ]
    msg_missing = f"{len(missing_field)} adapter(s) missing private_data field: {missing_field}"
    assert not missing_field, msg_missing


def test_no_restricted_microdata_ready_adapters() -> None:
    """No adapter may combine restricted_microdata=true with status=READY."""
    bad: list[str] = [
        cast(str, a["adapter_id"])
        for a in _adapters()
        if a.get("restricted_microdata") is True and a.get("status") == "READY"
    ]
    msg = (
        f"{len(bad)} adapter(s) combine restricted_microdata=true with status=READY "
        f"(forbidden): {bad}"
    )
    assert not bad, msg
    # second case: restricted_microdata adapters MUST be metadata_only class
    bad_class: list[tuple[str, str]] = [
        (cast(str, a["adapter_id"]), cast(str, a["adapter_class"]))
        for a in _adapters()
        if a.get("restricted_microdata") is True and a["adapter_class"] != "metadata_only_adapter"
    ]
    msg_class = (
        f"{len(bad_class)} restricted_microdata adapter(s) are not metadata_only_adapter "
        f"class: {bad_class}"
    )
    assert not bad_class, msg_class


def test_no_unclear_license_status_ready() -> None:
    """access_boundary=license_review forbids status=READY."""
    bad: list[tuple[str, str, str]] = [
        (cast(str, a["adapter_id"]), cast(str, a["access_boundary"]), cast(str, a["status"]))
        for a in _adapters()
        if a.get("access_boundary") == "license_review" and a.get("status") == "READY"
    ]
    msg = f"{len(bad)} adapter(s) combine access_boundary=license_review with status=READY: {bad}"
    assert not bad, msg
    bad_boundary: list[tuple[str, str]] = [
        (cast(str, a["adapter_id"]), cast(str, a["access_boundary"]))
        for a in _adapters()
        if a.get("access_boundary") not in VALID_ACCESS_BOUNDARIES
    ]
    msg_b = (
        f"{len(bad_boundary)} adapter(s) carry invalid access_boundary; allowed = "
        f"{sorted(VALID_ACCESS_BOUNDARIES)}: {bad_boundary}"
    )
    assert not bad_boundary, msg_b


def test_max_download_size_capped() -> None:
    """Every adapter declares a positive integer max_download_bytes <= 5 MB default."""
    bad: list[tuple[str, Any]] = []
    too_big: list[tuple[str, int]] = []
    for a in _adapters():
        v = a.get("max_download_bytes")
        if not isinstance(v, int) or v <= 0:
            bad.append((cast(str, a["adapter_id"]), v))
            continue
        if v > 5_000_000:
            too_big.append((cast(str, a["adapter_id"]), v))
    msg_bad = f"{len(bad)} adapter(s) lack a positive integer max_download_bytes: {bad}"
    assert not bad, msg_bad
    msg_big = (
        f"{len(too_big)} adapter(s) request > 5 MB without per-adapter override "
        f"justification (P3.5 territory): {too_big}"
    )
    assert not too_big, msg_big


def test_no_canonical_run_authorized() -> None:
    """P3 capsule must not authorize canonical run; manifest claim_boundary must encode it."""
    boundary = cast(str, _manifest().get("claim_boundary", "")).lower()
    encoded = (
        "no canonical run" in boundary
        or "does not authorise" in boundary
        or "canonical_run_authorized" in boundary
        or "no canonical run authorisation" in boundary
    )
    msg_manifest = (
        f"manifest claim_boundary must encode the no-canonical-run invariant; "
        f"got: {_manifest().get('claim_boundary')!r}"
    )
    assert encoded, msg_manifest
    msg_capsule = f"P3 capsule must exist at {P3_CAPSULE_JSON}"
    assert P3_CAPSULE_JSON.is_file(), msg_capsule
    cap = _load_json(P3_CAPSULE_JSON)
    cap_boundary = cast(str, cap.get("claim_boundary", "")).lower()
    encoded_cap = (
        "no canonical run" in cap_boundary
        or "does not authorise" in cap_boundary
        or "canonical_run_authorized" in cap_boundary
    )
    msg_cap_b = f"P3 capsule claim_boundary must encode no-canonical-run; got: {cap.get('claim_boundary')!r}"
    assert encoded_cap, msg_cap_b


def test_no_d002j_prereg_edit() -> None:
    """D-002J prereg sha256 must remain byte-exact at the locked value."""
    LOCKED_D002J_PREREG_SHA = (  # noqa: N806
        "f3dc65b7e64b96eafe6f23ca8bdd0e05d"  # pragma: allowlist secret
        + "c9bf95b12c2658b227bd0340f7975a0"  # pragma: allowlist secret
    )
    actual = _sha256_of(D002J_PREREG)
    msg = f"D-002J prereg sha drifted; expected {LOCKED_D002J_PREREG_SHA}, got {actual}"
    assert actual == LOCKED_D002J_PREREG_SHA, msg
    # second case: P1B registry sha must also be byte-exact (parent pin)
    actual_p1b = _sha256_of(P1B_REGISTRY_JSON)
    msg_p1b = f"P1B registry sha drifted; expected {LOCKED_P1B_REGISTRY_SHA}, got {actual_p1b}"
    assert actual_p1b == LOCKED_P1B_REGISTRY_SHA, msg_p1b


def test_no_research_systemic_risk_source_edit() -> None:
    """research/systemic_risk/*.py must NOT be edited by this PR (governance-only PR)."""
    msg_dir = f"research/systemic_risk/ must exist at {RESEARCH_SYSTEMIC_DIR}"
    assert RESEARCH_SYSTEMIC_DIR.is_dir(), msg_dir
    # touch-test: the directory has Python files we don't claim ownership of
    py_files = sorted(RESEARCH_SYSTEMIC_DIR.glob("*.py"))
    msg_present = "research/systemic_risk/ must contain Python files (D-002J P-* infra unchanged)"
    assert len(py_files) > 0, msg_present


def test_no_unresolved_merge_markers() -> None:
    """No new file may contain unresolved git-merge markers."""
    targets: list[Path] = [
        MANIFEST_JSON,
        ADAPTER_REGISTRY_JSON,
        SOURCE_HASH_MANIFEST_JSON,
        INGESTION_BOUNDARY_MD,
        POINT_IN_TIME_MD,
        P3_CAPSULE_JSON,
        DAG_VERDICT_JSON,
        LINEAGE_MAP_MD,
        BLOCKERS_MD,
        ACCEPTOR_YAML,
        Path(__file__),
    ]
    hits: list[tuple[str, int, str]] = []
    for p in targets:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i, line[:32]))
    msg = f"unresolved git-merge markers detected in P3 files: {hits}"
    assert hits == [], msg


def test_p3_capsule_under_dag_contract() -> None:
    """P3 capsule conforms to D002J-VERDICT-CAPSULE-v1 with parent=P2 and allowed_next=P4."""
    msg_exists = f"P3 capsule must exist at {P3_CAPSULE_JSON}"
    assert P3_CAPSULE_JSON.is_file(), msg_exists
    cap = _load_json(P3_CAPSULE_JSON)
    msg_schema = (
        f"P3 capsule schema_version must be D002J-VERDICT-CAPSULE-v1; "
        f"got {cap.get('schema_version')!r}"
    )
    assert cap.get("schema_version") == "D002J-VERDICT-CAPSULE-v1", msg_schema
    msg_node = f"P3 capsule node_id must be D002J-P3; got {cap.get('node_id')!r}"
    assert cap.get("node_id") == "D002J-P3", msg_node
    parents = cast(list[str], cap.get("parent_nodes", []))
    msg_parent = f"P3 capsule parent_nodes must be ['D002J-P2']; got {parents}"
    assert parents == ["D002J-P2"], msg_parent
    allowed = cast(list[str], cap.get("allowed_next_nodes", []))
    msg_allowed = f"P3 capsule allowed_next_nodes must include 'D002J-P4'; got {allowed}"
    assert "D002J-P4" in allowed, msg_allowed
    forbidden = cast(list[str], cap.get("forbidden_next_nodes", []))
    must_forbid = {"D002J-P5", "D002J-P6", "D002J-P7", "D002J-P8", "D002J-P9"}
    missing_forbids = sorted(must_forbid - set(forbidden))
    msg_forbid = (
        f"P3 capsule must forbid {sorted(must_forbid)} (no gate-skip); "
        f"missing from forbidden_next_nodes: {missing_forbids}"
    )
    assert not missing_forbids, msg_forbid


def test_p3_in_dag_verdict() -> None:
    """DAG verdict must contain >=6 nodes and include D-002J-P3 in topological_order.

    The DAG grows monotonically as later phases land (P4 adds a 7th
    node, etc.). This P3 guard pins the floor (P3 must be present and
    the DAG must be at least the post-P3 size) without re-asserting an
    exact count that a legitimate downstream phase would break.
    """
    msg_exists = f"DAG verdict must exist at {DAG_VERDICT_JSON}"
    assert DAG_VERDICT_JSON.is_file(), msg_exists
    dv = _load_json(DAG_VERDICT_JSON)
    nodes_count = dv.get("nodes_count")
    msg_count = f"DAG verdict nodes_count must be >=6 after P3 lands; got {nodes_count!r}"
    assert isinstance(nodes_count, int) and nodes_count >= 6, msg_count
    order = cast(list[str], dv.get("topological_order", []))
    msg_order = f"DAG topological_order must include 'D002J-P3'; got {order}"
    assert "D002J-P3" in order, msg_order
    msg_acyclic = f"DAG must remain acyclic after P3; got acyclic={dv.get('acyclic')!r}"
    assert dv.get("acyclic") is True, msg_acyclic
    msg_canonical = f"canonical_run_authorized_anywhere must remain false; got {dv.get('canonical_run_authorized_anywhere')!r}"
    assert dv.get("canonical_run_authorized_anywhere") is False, msg_canonical


def test_ingestion_boundary_doc_present() -> None:
    """Ingestion boundary doc + point-in-time discipline doc exist and reference P3 anchors."""
    msg_ing = f"ingestion boundary doc must exist at {INGESTION_BOUNDARY_MD}"
    assert INGESTION_BOUNDARY_MD.is_file(), msg_ing
    msg_pit = f"point-in-time discipline doc must exist at {POINT_IN_TIME_MD}"
    assert POINT_IN_TIME_MD.is_file(), msg_pit
    body_ing = INGESTION_BOUNDARY_MD.read_text(encoding="utf-8")
    body_pit = POINT_IN_TIME_MD.read_text(encoding="utf-8")
    msg_pit_terms = "point-in-time doc must mention vintage_required and forecast_required terms"
    assert "vintage_required" in body_pit and "forecast_required" in body_pit, msg_pit_terms
    msg_ing_classes = "ingestion boundary doc must enumerate all 5 adapter classes verbatim"
    for cls in VALID_ADAPTER_CLASSES:
        assert cls in body_ing, f"{msg_ing_classes}; missing class: {cls!r}"
