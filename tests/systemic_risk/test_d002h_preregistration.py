# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H — Pre-registration lock invariants.

These tests pin the fresh-lineage pre-registration artifact landed in
this PR. They fail-closed on:

* the D-002H YAML or JSON lock being missing, malformed, or carrying
  a different study identifier;
* the substrate scope drifting from {ricci_flow} included /
  {block_structured, temporal_coupling} excluded;
* the forbidden-claims set dropping any of the canonical phrases
  (cross-substrate robustness, general topology robustness, D-002G
  rescue, ...);
* the canonical_run_authorized flag flipping to True or the
  requires_explicit_authorization_artifact flag flipping to False;
* the parent-closure sha diverging from the locked anchor;
* the lineage_type or edit_policy fields drifting away from
  fresh_preregistration / fresh_pre_registration_only;
* the verbatim claim-boundary block being stripped from
  D002H_CLAIM_BOUNDARY.md;
* a byte-level mutation of docs/governance/D002C_CLAIM_LEDGER.yaml
  (sha256 pin verified against the cross-PR locked anchor);
* a byte-level mutation of research/systemic_risk/d002c_substrates.py
  (sha256 pin verified against the parent-closure base sha).

Lineage scope: D-002H is a FRESH pre-registration. It does NOT amend
D-002G. It does NOT rescue D-002C. It does NOT authorise canonical
run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV = REPO_ROOT / "docs" / "governance"

PREREG_YAML = GOV / "D002H_PREREGISTRATION.yaml"
CLAIM_BOUNDARY = GOV / "D002H_CLAIM_BOUNDARY.md"
PREREG_LOCK_JSON = REPO_ROOT / "artifacts" / "d002h" / "prereg" / "d002h_preregistration_lock.json"
D002C_LEDGER = GOV / "D002C_CLAIM_LEDGER.yaml"
SUBSTRATES_PY = REPO_ROOT / "research" / "systemic_risk" / "d002c_substrates.py"

PARENT_CLOSURE_SHA = "8cf5364a3f3b605d8b134bccbfe5170098e0e197"

# fmt: off
D002C_LEDGER_SHA256 = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
SUBSTRATES_PY_SHA256_AT_BASE = "4b2e5d65c104a5be5a207951cd3c4ae099f31ce83b3f2c0766a160d8c9e80eca"  # noqa: E501  # pragma: allowlist secret
# fmt: on


def _load_yaml() -> dict[str, Any]:
    with PREREG_YAML.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    assert isinstance(loaded, dict), "D002H prereg yaml must load as mapping"
    return loaded


def _load_lock_json() -> dict[str, Any]:
    with PREREG_LOCK_JSON.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert isinstance(loaded, dict), "d002h lock json must be an object"
    return loaded


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_d002h_prereg_exists() -> None:
    """YAML exists; parses; has top-level study_id == 'D-002H'."""
    assert PREREG_YAML.exists(), f"missing D-002H prereg: {PREREG_YAML}"
    data = _load_yaml()
    assert data.get("study_id") == "D-002H", "D-002H prereg study_id must be 'D-002H'"
    assert data.get("schema_version") == "D002H-PREREGISTRATION-v1"


def test_d002h_scope_is_ricci_flow_only() -> None:
    """substrate_scope.included == ['ricci_flow'] exactly."""
    data = _load_yaml()
    included = data["substrate_scope"]["included"]
    assert included == ["ricci_flow"], "D-002H included substrates must be exactly ['ricci_flow']"


def test_d002h_excludes_block_structured() -> None:
    """block_structured must be excluded and the exclusion reason must
    cite the seed-deterministic root cause."""
    data = _load_yaml()
    excluded = data["substrate_scope"]["excluded"]
    assert "block_structured" in excluded, "block_structured must be in substrate_scope.excluded"
    reason = data["exclusion_reason"]["block_structured"]
    assert "seed-deterministic" in reason.lower(), "must cite 'seed-deterministic' root cause"


def test_d002h_excludes_temporal_coupling() -> None:
    """temporal_coupling must be excluded and the exclusion reason must
    cite the delegation/inheritance chain to BlockStructuredSubstrate."""
    data = _load_yaml()
    excluded = data["substrate_scope"]["excluded"]
    assert "temporal_coupling" in excluded, "temporal_coupling must be in excluded"
    reason = data["exclusion_reason"]["temporal_coupling"].lower()
    assert "inherit" in reason, "temporal_coupling exclusion must cite inheritance"
    assert "delegation" in reason, "temporal_coupling exclusion must cite delegation"


def test_d002h_forbids_cross_substrate_claims() -> None:
    """forbidden_claims must contain the two cross-substrate phrases verbatim."""
    data = _load_yaml()
    forbidden = data["forbidden_claims"]
    assert "cross-substrate robustness" in forbidden, "missing 'cross-substrate robustness'"
    assert "general topology robustness" in forbidden, "missing 'general topology robustness'"


def test_d002h_forbids_d002g_rescue_claim() -> None:
    """forbidden_claims must contain 'D-002G rescue' verbatim."""
    data = _load_yaml()
    forbidden = data["forbidden_claims"]
    assert "D-002G rescue" in forbidden, "forbidden_claims must contain 'D-002G rescue'"


def test_d002h_forbids_canonical_run_without_authorization() -> None:
    """canonical_run_authorized MUST be False AND
    requires_explicit_authorization_artifact MUST be True."""
    data = _load_yaml()
    assert data["canonical_run_authorized"] is False, "D-002H MUST NOT authorise canonical run"
    assert data["requires_explicit_authorization_artifact"] is True, "must require auth artifact"


def test_d002h_preserves_d002c_ledger() -> None:
    """D-002C claim ledger must be byte-exact at the locked sha256 pin.

    The pin below is the canonical D-002C ledger anchor; D-002H MUST NOT
    mutate it.
    """
    actual = _sha256_of(D002C_LEDGER)
    assert actual == D002C_LEDGER_SHA256, (
        f"D002C_CLAIM_LEDGER.yaml sha256 drift: "
        f"expected {D002C_LEDGER_SHA256}, got {actual}. "
        f"D-002H MUST NOT mutate the D-002C ledger."
    )


def test_d002h_parent_closure_sha_pinned() -> None:
    """YAML parent_merge_sha and JSON lock parent_merge_sha must both
    match the D-002G structural closure merge sha."""
    data = _load_yaml()
    assert data["parent_merge_sha"] == PARENT_CLOSURE_SHA, "yaml parent_merge_sha drift"
    lock = _load_lock_json()
    assert lock["parent_merge_sha"] == PARENT_CLOSURE_SHA, "json lock parent_merge_sha drift"


def test_d002h_requires_fresh_lineage() -> None:
    """lineage_type == 'fresh_preregistration' AND
    prereg_lock.edit_policy == 'fresh_pre_registration_only'."""
    data = _load_yaml()
    assert data["lineage_type"] == "fresh_preregistration", "lineage_type drift"
    edit_policy = data["prereg_lock"]["edit_policy"]
    assert edit_policy == "fresh_pre_registration_only", "edit_policy drift"


def test_d002h_claim_boundary_verbatim_present() -> None:
    """The verbatim claim-boundary paragraph must live in D002H_CLAIM_BOUNDARY.md."""
    assert CLAIM_BOUNDARY.exists(), f"missing claim-boundary doc: {CLAIM_BOUNDARY}"
    text = CLAIM_BOUNDARY.read_text(encoding="utf-8")
    expected_block = (
        "D-002H is scoped to ricci_flow only. "
        "It does not claim cross-substrate robustness. "
        "It does not rescue D-002G. "
        "It does not update D-002C. "
        "It does not authorize canonical run until a separate "
        "authorization artifact passes all gates. "
        "Any result from D-002H is valid only inside the ricci_flow substrate boundary."
    )
    assert expected_block in text, "claim-boundary doc missing verbatim paragraph"


def test_d002h_no_substrate_code_touch() -> None:
    """research/systemic_risk/d002c_substrates.py must be byte-exact unchanged
    at the D-002G structural-closure base sha. D-002H is documentation-only."""
    actual = _sha256_of(SUBSTRATES_PY)
    assert actual == SUBSTRATES_PY_SHA256_AT_BASE, (
        f"d002c_substrates.py sha256 drift: "
        f"expected {SUBSTRATES_PY_SHA256_AT_BASE} (base sha "
        f"{PARENT_CLOSURE_SHA}), got {actual}. "
        f"D-002H MUST NOT modify substrate code."
    )
