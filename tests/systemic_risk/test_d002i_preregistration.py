# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002I — pre-registration locking tests.

D-002I is a fresh pre-registration that locks 4 falsifiable hypotheses
(H_I1..H_I4) about WHY the D-002H canonical sweep null audit FAILed
on 42 / 54 audited cells. D-002I is investigation, not validation —
it does NOT propose a mechanism change, does NOT authorise a new
canonical sweep, and does NOT rewrite the D-002H REFUSED canonical
verdict. Each hypothesis is tested in a separate downstream PR
(D-002I-P1/H1..H4) under a pre-committed protocol.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG_YAML = REPO_ROOT / "docs" / "governance" / "D002I_PREREGISTRATION.yaml"
RATIONALE_MD = REPO_ROOT / "docs" / "governance" / "D002I_INVESTIGATION_RATIONALE.md"
CLAIM_BOUNDARY_MD = REPO_ROOT / "docs" / "governance" / "D002I_CLAIM_BOUNDARY.md"
PREREG_LOCK_JSON = REPO_ROOT / "artifacts" / "d002i" / "prereg" / "d002i_preregistration_lock.json"

# D-002G acceptance rules locked sha256.  # pragma: allowlist secret
LOCKED_D002G_ACCEPTANCE_SHA = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"
# D-002H prereg locked sha256.  # pragma: allowlist secret
LOCKED_D002H_PREREG_SHA = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"
# D-002C claim ledger sha256 at D-002I prereg-lock anchor.  # pragma: allowlist secret
LOCKED_D002C_LEDGER_SHA = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"
# D-002C claim ledger sha256 post-D-002H-REFUSED-append (PR #692).  # pragma: allowlist secret
LOCKED_D002C_LEDGER_SHA_POST_APPEND = (
    "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"
)
PARENT_CANONICAL_SHA = "250d8069d16ecabdb49b5a20b7cf1d622eddc925"
HYPOTHESIS_IDS = ("H_I1", "H_I2", "H_I3", "H_I4")

CLAIM_BOUNDARY_VERBATIM = (
    "D-002I is investigation, not validation. It does NOT claim D-002H "
    "REFUSED was wrong (the verdict was truthful). It does NOT propose "
    "mechanism changes — those are separate D-002J pre-registrations. "
    "Each H_I1..H_I4 investigation produces a SCOPED SUPPORTED/REFUTED "
    "verdict only."
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_prereg() -> dict[str, Any]:
    with PREREG_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _load_lock_json() -> dict[str, Any]:
    with PREREG_LOCK_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _hypotheses(source: dict[str, Any]) -> list[dict[str, Any]]:
    hyps = source["hypotheses"]
    assert isinstance(hyps, list)
    out: list[dict[str, Any]] = []
    for h in hyps:
        assert isinstance(h, dict)
        out.append(cast(dict[str, Any], h))
    return out


def _str_list(source: dict[str, Any], key: str) -> list[str]:
    value = source[key]
    assert isinstance(value, list)
    return [str(item) for item in value]


def test_d002i_prereg_exists() -> None:
    """The pre-registration YAML and JSON lock both exist on disk."""
    assert PREREG_YAML.exists(), f"missing: {PREREG_YAML}"
    assert PREREG_LOCK_JSON.exists(), f"missing: {PREREG_LOCK_JSON}"
    assert RATIONALE_MD.exists(), f"missing: {RATIONALE_MD}"
    assert CLAIM_BOUNDARY_MD.exists(), f"missing: {CLAIM_BOUNDARY_MD}"


def test_d002i_4_hypotheses_pinned() -> None:
    """Exactly 4 hypotheses, with the canonical IDs H_I1..H_I4."""
    for source in (_load_prereg(), _load_lock_json()):
        hyps = _hypotheses(source)
        assert len(hyps) == 4, f"expected 4 hypotheses, got {len(hyps)}"
        ids = tuple(str(h["id"]) for h in hyps)
        assert ids == HYPOTHESIS_IDS, f"hypothesis IDs out of order: {ids}"


def test_d002i_each_hypothesis_has_falsification_protocol() -> None:
    """Each of H_I1..H_I4 ships a non-empty falsification_protocol string."""
    for source in (_load_prereg(), _load_lock_json()):
        for h in _hypotheses(source):
            proto = h.get("falsification_protocol")
            assert (
                isinstance(proto, str) and proto.strip()
            ), f"hypothesis {h.get('id')} missing falsification_protocol"
            # Each protocol must name its D-002I-P1/Hn downstream PR tag.
            hid = str(h["id"])
            tag = f"D-002I-P1/{hid[2:]}"
            assert (
                tag in proto or "D-002I-P1/H" in proto
            ), f"hypothesis {hid} protocol must reference its D-002I-P1/Hn PR tag"


def test_d002i_each_hypothesis_has_support_and_refutation_criterion() -> None:
    """Each of H_I1..H_I4 ships both support_criterion AND refutation_criterion."""
    for source in (_load_prereg(), _load_lock_json()):
        for h in _hypotheses(source):
            sup = h.get("support_criterion")
            ref = h.get("refutation_criterion")
            assert (
                isinstance(sup, str) and sup.strip()
            ), f"hypothesis {h.get('id')} missing support_criterion"
            assert (
                isinstance(ref, str) and ref.strip()
            ), f"hypothesis {h.get('id')} missing refutation_criterion"


def test_d002i_parent_canonical_run_sha_pinned() -> None:
    """Parent D-002H canonical-sweep merge sha is byte-pinned (250d8069...)."""
    yaml_data = _load_prereg()
    assert str(yaml_data["parent_canonical_run_merge_sha"]) == PARENT_CANONICAL_SHA
    assert str(yaml_data["parent_canonical_run_verdict"]) == "REFUSED_NULL_AUDIT_FAIL_D002H"
    lock_data = _load_lock_json()
    assert str(lock_data["parent_canonical_run_merge_sha"]) == PARENT_CANONICAL_SHA
    assert str(lock_data["parent_canonical_run_verdict"]) == "REFUSED_NULL_AUDIT_FAIL_D002H"


def test_d002i_substrate_scope_ricci_flow_only() -> None:
    """substrate_scope.included == [ricci_flow]; excluded list intact."""
    for source in (_load_prereg(), _load_lock_json()):
        scope = source["substrate_scope"]
        assert isinstance(scope, dict)
        scope_d = cast(dict[str, Any], scope)
        included = [str(x) for x in cast(list[Any], scope_d["included"])]
        excluded = [str(x) for x in cast(list[Any], scope_d["excluded"])]
        assert included == ["ricci_flow"]
        assert "block_structured" in excluded
        assert "temporal_coupling" in excluded


def test_d002i_forbids_post_hoc_substrate_redesign() -> None:
    """Substrate code edit is explicitly disallowed under H_I3 parameter set."""
    yaml_data = _load_prereg()
    param_sets = yaml_data["hypothesis_parameter_sets"]
    assert isinstance(param_sets, dict)
    h_i3_params = cast(dict[str, Any], param_sets)["H_I3"]
    assert isinstance(h_i3_params, dict)
    assert cast(dict[str, Any], h_i3_params)["substrate_code_edit"] is False

    lock_h_i3 = next(h for h in _hypotheses(_load_lock_json()) if h["id"] == "H_I3")
    param_set = lock_h_i3["parameter_set"]
    assert isinstance(param_set, dict)
    assert cast(dict[str, Any], param_set)["substrate_code_edit"] is False


def test_d002i_forbids_d002h_rescue_claim() -> None:
    """D-002H rescue, PASS claim, and canonical-sweep authorisation are forbidden."""
    for source in (_load_prereg(), _load_lock_json()):
        forbidden = _str_list(source, "forbidden_claims")
        assert any("D-002I will produce D-002H PASS" in c for c in forbidden)
        assert any("D-002I rescues D-002H" in c for c in forbidden)
        assert any("D-002I rescues D-002G or D-002C" in c for c in forbidden)
        assert any("D-002I authorises a new canonical sweep" in c for c in forbidden)


def test_d002i_no_canonical_run_authorisation() -> None:
    """canonical_run_authorized == False, investigation_only == True."""
    for source in (_load_prereg(), _load_lock_json()):
        assert source["canonical_run_authorized"] is False
        assert source["investigation_only"] is True


def test_d002i_preserves_d002c_ledger() -> None:
    """D-002I prereg pins D-002C ledger sha at the historical prereg anchor.

    The YAML field ``relationship_to_d002c.d002c_ledger_sha_at_d002i_prereg``
    records the ledger sha AT D-002I PREREG LOCK — must remain byte-exact.
    The live disk sha rotates legitimately under the PR #692 D-002H
    REFUSED entry append (a separate append-only governance event).
    """
    ledger_path = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
    assert ledger_path.exists()
    yaml_data = _load_prereg()
    rel = yaml_data["relationship_to_d002c"]
    assert isinstance(rel, dict)
    assert (
        str(cast(dict[str, Any], rel)["d002c_ledger_sha_at_d002i_prereg"])
        == LOCKED_D002C_LEDGER_SHA
    ), "D-002I prereg yaml field d002c_ledger_sha_at_d002i_prereg drift."
    live_sha = _sha256(ledger_path)
    assert live_sha in {
        LOCKED_D002C_LEDGER_SHA,
        LOCKED_D002C_LEDGER_SHA_POST_APPEND,
    }, (
        f"D-002C claim ledger live disk sha {live_sha!r} is neither the "
        f"D-002I prereg-lock anchor nor the post-D-002H-REFUSED-append anchor."
    )


def test_d002i_preserves_d002h_prereg() -> None:
    """D-002H pre-registration sha256 stays byte-exact at its locked anchor."""
    d002h_prereg = REPO_ROOT / "docs" / "governance" / "D002H_PREREGISTRATION.yaml"
    assert d002h_prereg.exists()
    assert (
        _sha256(d002h_prereg) == LOCKED_D002H_PREREG_SHA
    ), "D-002H prereg sha256 drift -- D-002I forbids any prereg edit."
    # D-002G acceptance rules also locked.
    d002g_rules = REPO_ROOT / "docs" / "governance" / "D002G_ACCEPTANCE_RULES.md"
    assert d002g_rules.exists()
    assert (
        _sha256(d002g_rules) == LOCKED_D002G_ACCEPTANCE_SHA
    ), "D-002G acceptance rules sha256 drift -- D-002I forbids any rules edit."


def test_d002i_claim_boundary_verbatim_present() -> None:
    """The verbatim claim-boundary block is present in D002I_CLAIM_BOUNDARY.md."""
    text = CLAIM_BOUNDARY_MD.read_text(encoding="utf-8")
    assert (
        CLAIM_BOUNDARY_VERBATIM in text
    ), "Verbatim claim-boundary block missing from D002I_CLAIM_BOUNDARY.md"


def test_d002i_prereg_lock_at_merge() -> None:
    """prereg_lock declares locked_at_merge=true; edit_policy = fresh_pre_registration_only."""
    yaml_data = _load_prereg()
    lock = yaml_data["prereg_lock"]
    assert isinstance(lock, dict)
    lock_d = cast(dict[str, Any], lock)
    assert lock_d["locked_at_merge"] is True
    assert str(lock_d["edit_policy"]) == "fresh_pre_registration_only"
    assert "D002K" in str(lock_d["edit_constitutes"])

    lock_data = _load_lock_json()
    assert lock_data["locked_at_merge"] is True
    assert str(lock_data["edit_policy"]) == "fresh_pre_registration_only"


def test_d002i_decision_tree_branches_named() -> None:
    """All three decision-tree branches are pre-committed (all REFUTED / 1 SUPPORTED / >=2 SUPPORTED)."""
    yaml_data = _load_prereg()
    tree = yaml_data["decision_tree"]
    assert isinstance(tree, list)
    branches: list[dict[str, Any]] = []
    for t in tree:
        assert isinstance(t, dict)
        branches.append(cast(dict[str, Any], t))
    assert len(branches) == 3
    conditions = {str(t["condition"]) for t in branches}
    assert any("all 4 hypotheses REFUTED" in c for c in conditions)
    assert any("exactly 1 hypothesis SUPPORTED" in c for c in conditions)
    assert any("≥ 2 hypotheses SUPPORTED" in c for c in conditions)
