# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G — Structural-closure artifact invariants.

These tests pin the negative-result retention artifact landed in this
PR. They fail-closed on:

* the closure report being missing or stripped of its verdict block;
* the JSON closure record drifting from schema_version v1, losing any
  of the four merge-chain entries, or flipping any of the boolean
  claim-boundary flags;
* a forbidden D-002G PASS / canonical-run authorisation phrase
  appearing in the closure docs or JSON outside an explicit denial
  context;
* a byte-level mutation of ``docs/governance/D002C_CLAIM_LEDGER.yaml``
  (sha256 pin verified against the cross-PR locked anchor);
* the negative-space map dropping any of the five mechanism rows;
* the closure documents losing the bottom-turtle ``_ = seed`` quote
  or the ``research/systemic_risk/d002c_substrates.py`` line-401
  citation;
* any "M4 implementation" / "M4 will fix" / "M4 inside D-002G"
  string outside an explicit forbidden-list / denial context;
* the ``legal_next_paths`` JSON list growing an M4-themed id or
  losing any of the three fresh-pre-registration ids;
* the ``D002G_CANONICAL_RUN_BLOCKERS.md`` losing any of its
  pre-existing section headings, or the new B1.closure subsection
  appearing before them in source order.

Closure scope: STRUCTURAL_CLOSURE on the conjunction (D-002G prereg
substrates x locked marginal set x M1/M2/M3 mechanism families).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV = REPO_ROOT / "docs" / "governance"

CLOSURE_REPORT = GOV / "D002G_STRUCTURAL_CLOSURE_REPORT.md"
NEGATIVE_SPACE_MAP = GOV / "D002G_NEGATIVE_SPACE_MAP.md"
CLOSURE_JSON = REPO_ROOT / "artifacts" / "d002g" / "closure" / "d002g_structural_closure.json"
BLOCKERS_DOC = GOV / "D002G_CANONICAL_RUN_BLOCKERS.md"
CLAIM_LEDGER = GOV / "D002C_CLAIM_LEDGER.yaml"
SUBSTRATES_PY = REPO_ROOT / "research" / "systemic_risk" / "d002c_substrates.py"

# fmt: off
_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# fmt: on

_MERGE_SHA_PREFIXES: tuple[str, ...] = (
    "d3400c2e",
    "7b386ef3",
    "0f4433e0",
    "cced6e60",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json() -> dict[str, Any]:
    raw = _read(CLOSURE_JSON)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssertionError("closure JSON payload must be a dict")
    return payload


def _require(cond: bool, msg: str) -> None:
    """Assert helper that survives black + ruff format without re-flow."""
    if not cond:
        raise AssertionError(msg)


_DENIAL_MARKERS: tuple[str, ...] = (
    "forbidden",
    " not ",
    " no ",
    " never",
    "cannot",
    "does not",
    "do not",
    "is not",
    "are not",
    "out of scope",
    "out-of-scope",
    "rejected",
    "claimed: false",
    '_claimed": false',
    "remains blocked",
    "remain blocked",
    "is blocked",
    "is_blocked",
    "conflates",
    "deferred",
    "untested",
    "must not",
    "would have demanded",
)


def _is_denial_context(lines: list[str], lineno: int) -> bool:
    """Return True if the line at ``lineno`` sits inside a denial paragraph.

    The protocol allows forbidden phrases inside denial bullets, denial
    sentences ("does NOT", "do NOT", "is not", "no scientific PASS"),
    forbidden-list blocks, and quoted-blockquote denials. Because
    markdown soft-wraps a denial sentence across multiple physical
    lines, the check inspects a small symmetric paragraph window
    around the candidate line (3 lines before, 3 lines after) and
    treats the candidate as denial-context if any window line carries
    a denial marker.
    """
    start = max(0, lineno - 4)
    end = min(len(lines), lineno + 3)
    window = "\n".join(lines[start:end]).lower()
    # The cross-mark character is added explicitly (kept out of the
    # ASCII marker list to keep the file safe under formatter pipelines).
    if "❌" in window:
        return True
    return any(marker in window for marker in _DENIAL_MARKERS)


# ---------------------------------------------------------------------------
# 1. closure report exists + verdict present
# ---------------------------------------------------------------------------


def test_closure_report_exists() -> None:
    """The closure report file exists and carries the verbatim verdict block."""
    _require(CLOSURE_REPORT.is_file(), f"closure report missing: {CLOSURE_REPORT}")
    body = _read(CLOSURE_REPORT)
    _require("STRUCTURAL CLOSURE" in body, "verdict block 'STRUCTURAL CLOSURE' missing")
    _require("STRUCTURALLY BLOCKED" in body, "verdict 'STRUCTURALLY BLOCKED' missing")
    _require("Canonical run remains BLOCKED" in body, "'Canonical run remains BLOCKED' missing")


# ---------------------------------------------------------------------------
# 2. JSON schema keys + boolean claim-boundary flags
# ---------------------------------------------------------------------------


def test_closure_json_schema_keys() -> None:
    """Closure JSON conforms to schema v1 with required boolean flags."""
    payload = _load_json()

    schema_v = payload["schema_version"]
    _require(schema_v == "D002G-STRUCTURAL-CLOSURE-v1", f"schema_version drift: {schema_v!r}")

    merge_chain = payload["merge_chain"]
    _require(isinstance(merge_chain, list), "merge_chain must be a list")
    assert isinstance(merge_chain, list)  # mypy narrow
    _require(len(merge_chain) == 4, f"merge_chain must have 4 entries, got {len(merge_chain)}")

    for entry in merge_chain:
        _require(isinstance(entry, dict), "merge_chain entry must be dict")
        assert isinstance(entry, dict)  # mypy narrow
        sha_val = entry["merge_sha"]
        _require(isinstance(sha_val, str), "merge_sha must be str")
        assert isinstance(sha_val, str)  # mypy narrow
        sha_prefix = sha_val[:8]
        _require(sha_prefix in _MERGE_SHA_PREFIXES, f"bad sha prefix {sha_prefix!r}")

    _require(payload["canonical_run_authorized"] is False, "canonical_run_authorized flipped")
    _require(payload["scientific_pass_claimed"] is False, "scientific_pass_claimed flipped")
    _require(payload["d002c_ledger_touched"] is False, "d002c_ledger_touched flipped")
    _require(
        payload["d002g_globally_falsified_claimed"] is False,
        "d002g_globally_falsified_claimed flipped",
    )
    _require(payload["ricci_flow_invalid_claimed"] is False, "ricci_flow_invalid_claimed flipped")

    b1_status = payload["b1_status"]
    _require(isinstance(b1_status, str), "b1_status must be str")
    assert isinstance(b1_status, str)  # mypy narrow
    _require(b1_status.startswith("OPEN_STRUCTURALLY_BLOCKED"), f"bad b1_status: {b1_status!r}")
    _require(payload["b2_status"] == "OPEN_UNTOUCHED", f"bad b2_status: {payload['b2_status']!r}")


# ---------------------------------------------------------------------------
# 3. forbidden canonical-run authorisation phrases
# ---------------------------------------------------------------------------


def _scan_forbidden(needles: tuple[str, ...], label: str) -> None:
    targets = (CLOSURE_REPORT, NEGATIVE_SPACE_MAP, CLOSURE_JSON)
    violations: list[str] = []
    for target in targets:
        lines = _read(target).splitlines()
        for idx, raw_line in enumerate(lines):
            lower = raw_line.lower()
            if not any(n in lower for n in needles):
                continue
            if _is_denial_context(lines, idx):
                continue
            violations.append(f"{target.name}:{idx + 1}: {raw_line.strip()}")
    if violations:
        msg = f"forbidden {label} phrase outside denial context:\n" + "\n".join(violations)
        raise AssertionError(msg)


def test_closure_forbids_canonical_run() -> None:
    """No 'canonical run authorized/authorised' assertion outside denial context."""
    needles = (
        "canonical run authorized",
        "canonical run authorised",
        "canonical-run authorized",
        "canonical-run authorised",
    )
    _scan_forbidden(needles, "canonical-run-authorisation")


# ---------------------------------------------------------------------------
# 4. forbidden D-002G scientific PASS phrases
# ---------------------------------------------------------------------------


def test_closure_forbids_scientific_pass() -> None:
    """No D-002G PASS / scientific-PASS assertion outside denial context."""
    needles = (
        "d-002g pass",
        "d002g pass",
        "d-002g validated",
        "d002g validated",
        "scientific pass achieved",
        "validated_real_bank_level_result",
        "tested_positive_real",
        "bank_level_precursor_confirmed",
        "gamma universality",
        "bank-level confirmed",
        "real-data validated",
    )
    _scan_forbidden(needles, "scientific-PASS")


# ---------------------------------------------------------------------------
# 5. D002C ledger byte-exact pin
# ---------------------------------------------------------------------------


def test_closure_preserves_d002c_ledger() -> None:
    """D002C_CLAIM_LEDGER.yaml sha256 byte-exact against locked pin."""
    _require(CLAIM_LEDGER.is_file(), f"locked ledger missing: {CLAIM_LEDGER}")
    digest = hashlib.sha256(CLAIM_LEDGER.read_bytes()).hexdigest()
    _require(digest == _LEDGER_SHA256_PIN, f"ledger sha256 mutated: {digest}")


# ---------------------------------------------------------------------------
# 6. negative-space map enumerates all five mechanism rows
# ---------------------------------------------------------------------------


def test_negative_space_map_mentions_all_four_prs() -> None:
    """Negative-space map enumerates all five exhausted mechanism families."""
    _require(NEGATIVE_SPACE_MAP.is_file(), f"negative-space map missing: {NEGATIVE_SPACE_MAP}")
    body = _read(NEGATIVE_SPACE_MAP)
    required_rows = (
        "M1 independent seed",
        "M2 edge-weight permutation",
        "M2 node-payload permutation",
        "M2 injection-sequence permutation",
        "M3 topology-conditioned independent realisation",
    )
    for row in required_rows:
        _require(row in body, f"negative-space map missing row: {row!r}")
    required_lessons = (
        "independent-seed null requires substrate stochasticity",
        "edge-weight permutation requires",
        "node-payload permutation requires",
        "injection-sequence permutation requires",
        "mechanisms conditioned on marginal set",
    )
    for lesson in required_lessons:
        _require(lesson in body, f"negative-space map missing lesson: {lesson!r}")


# ---------------------------------------------------------------------------
# 7. bottom-turtle seed-ignored fact present
# ---------------------------------------------------------------------------


def test_bottom_turtle_seed_ignored_fact_present() -> None:
    """Closure report quotes the substrate-line-401 ``_ = seed`` fact."""
    body = _read(CLOSURE_REPORT)
    _require("_ = seed" in body, "closure report missing ``_ = seed`` quote")
    _require(
        "research/systemic_risk/d002c_substrates.py" in body,
        "closure report missing substrate file path citation",
    )
    _require("401" in body, "closure report missing line-401 citation")

    # Verify the cited substrate line truly contains the quoted fact.
    src_lines = _read(SUBSTRATES_PY).splitlines()
    _require(len(src_lines) >= 401, "substrate source shorter than expected")
    window = "\n".join(src_lines[395:405])
    _require("_ = seed" in window, "substrate source missing ``_ = seed`` near line 401")

    payload = _load_json()
    bottom = payload["bottom_turtle"]
    _require(isinstance(bottom, dict), "bottom_turtle must be dict")
    assert isinstance(bottom, dict)  # mypy narrow
    _require(bottom["line"] == 401, f"bottom_turtle.line must be 401, got {bottom['line']!r}")


# ---------------------------------------------------------------------------
# 8. no M4-implementation-in-D-002G claim
# ---------------------------------------------------------------------------


def test_no_m4_implementation_claim() -> None:
    """No 'M4 implementation' / 'M4 will fix' assertion outside denial context."""
    needles = (
        "m4 implementation",
        "m4 will fix",
        "m4 inside d-002g",
        "m4 inside d002g",
        "m4 mechanism inside d-002g",
        "m4 mechanism inside d002g",
    )
    _scan_forbidden(needles, "M4-implementation")


# ---------------------------------------------------------------------------
# 9. legal_next_paths are fresh-pre-registration ids only
# ---------------------------------------------------------------------------


def test_legal_next_paths_are_fresh_prereg_only() -> None:
    """legal_next_paths == 3 fresh-pre-reg ids; no M4-themed entry."""
    payload = _load_json()
    paths = payload["legal_next_paths"]
    _require(isinstance(paths, list), "legal_next_paths must be a list")
    assert isinstance(paths, list)  # mypy narrow
    _require(len(paths) == 3, f"legal_next_paths must have 3 entries, got {len(paths)}")

    seen_ids: list[str] = []
    for entry in paths:
        _require(isinstance(entry, dict), "legal_next_paths entry must be dict")
        assert isinstance(entry, dict)  # mypy narrow
        path_id = entry["id"]
        _require(isinstance(path_id, str), "legal_next_paths id must be str")
        assert isinstance(path_id, str)  # mypy narrow
        seen_ids.append(path_id)
        is_d002h = path_id.startswith("D002H_")
        is_retention = path_id == "D002G_NEGATIVE_ARTIFACT_RETENTION"
        _require(is_d002h or is_retention, f"bad legal_next_paths id: {path_id!r}")
        _require("M4" not in path_id, f"legal_next_paths id contains M4: {path_id!r}")

    expected_ids = {
        "D002H_SCOPE_NARROWING",
        "D002H_SUBSTRATE_REDESIGN",
        "D002G_NEGATIVE_ARTIFACT_RETENTION",
    }
    _require(set(seen_ids) == expected_ids, f"legal_next_paths ids drift: {sorted(seen_ids)}")


# ---------------------------------------------------------------------------
# 10. BLOCKERS.md appended, not rewritten
# ---------------------------------------------------------------------------


def test_blocker_doc_appended_not_rewritten() -> None:
    """The new B1.closure subsection appends after all prior B1/B2 sections."""
    body = _read(BLOCKERS_DOC)

    pre_existing_headings = (
        "### B1 — Substrate eligibility",
        "#### B1.M2 — Mitigation status",
        "#### B1.M3 — Topology-conditioned null mitigation status",
        "### B2 — Phase 0b CI is percentile bootstrap",
    )
    indices: list[int] = []
    for heading in pre_existing_headings:
        idx = body.find(heading)
        _require(idx >= 0, f"BLOCKERS.md missing pre-existing heading: {heading!r}")
        indices.append(idx)

    closure_marker = "#### B1.closure — Structural closure under current locked grid"
    closure_idx = body.find(closure_marker)
    _require(closure_idx >= 0, f"BLOCKERS.md missing closure subsection: {closure_marker!r}")

    b1_main_idx, b1_m2_idx, b1_m3_idx, b2_idx = indices
    _require(closure_idx > b1_main_idx, "B1.closure must come after B1 main")
    _require(closure_idx > b1_m2_idx, "B1.closure must come after B1.M2")
    _require(closure_idx > b1_m3_idx, "B1.closure must come after B1.M3")
    _require(closure_idx < b2_idx, "B1.closure must remain inside the B1 block (before B2)")

    closure_body_window = body[closure_idx : closure_idx + 1500]
    _require(
        "D002G_STRUCTURAL_CLOSURE_REPORT.md" in closure_body_window,
        "B1.closure must cite D002G_STRUCTURAL_CLOSURE_REPORT.md",
    )
    _require(
        re.search(r"cced6e60", closure_body_window) is not None,
        "B1.closure must cite PR #681 merge sha (cced6e60)",
    )
