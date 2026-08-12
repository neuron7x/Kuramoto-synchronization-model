# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H canonical-run artifact contract tests.

The D-002H canonical sweep (``scripts/x10r_d002h_canonical_sweep.py``)
produces a top-level verdict capsule at
``artifacts/d002h/canonical/d002h_canonical_run_verdict.json``. These
tests pin its schema, the locked grid (matching the D-002H prereg
verbatim), the 2-mechanism null set (M1 + M3 only, NOT M6), the R2-B
inapplicability assertion, the per-cell verdict cardinality (18), the
locked tier-string enum, aggregate-verdict consistency with cells,
the D-002C ledger preservation invariant, and the anti-overclaim
guards.

Lessons applied:
  * L1 -- N/A (tests only).
  * L2 -- pinned sha values carry ``# pragma: allowlist secret`` to
    bypass detect-secrets HexHighEntropy false-positives.
  * L3 -- every assertion has a descriptive ``msg_*`` variable.
  * L4 -- every test has >= 2 assertions or >= 2 distinct cases.
  * L5 -- zero broad-except in this file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_VERDICT_RELPATH = "artifacts/d002h/canonical/d002h_canonical_run_verdict.json"
CANONICAL_VERDICT_PATH = REPO_ROOT / CANONICAL_VERDICT_RELPATH

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
D002G_ACCEPTANCE_RELPATH = "docs/governance/D002G_ACCEPTANCE_RULES.md"
R2B_NOTE_RELPATH = "docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md"

# fmt: off
# Live (post-append) disk anchor: sha256 of the on-disk ledger AFTER the
# legitimate D-002H REFUSED entry append in PR #692.
D002C_LEDGER_SHA_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# Frozen pre-append anchor: the canonical-run verdict artifact records
# the ledger sha AT THE TIME the canonical sweep executed (PR #691),
# which is the pre-append historical sha. The artifact stays unchanged;
# only the live disk has rotated.
D002C_LEDGER_SHA_PRE_APPEND: str = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"  # noqa: E501  # pragma: allowlist secret  # frozen at canonical-run anchor; pre-D-002H-REFUSED-append
D002H_PREREG_SHA_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
D002G_ACCEPTANCE_SHA_PIN: str = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"  # noqa: E501  # pragma: allowlist secret
ANCHOR_MAIN_SHA: str = "ee12a9e6a08e5916109c99eec84796d1e1375cd0"  # noqa: E501  # pragma: allowlist secret
# fmt: on

EXPECTED_SCHEMA = "D002H-CANONICAL-RUN-VERDICT-v1"
EXPECTED_STUDY_ID = "D-002H"
EXPECTED_RUN_ID = "d002h_ricci_flow_canonical_v1_2026-05-14"

EXPECTED_N_GRID = [50, 100, 200]
EXPECTED_LAMBDA_GRID = [0.0, 0.05, 0.10, 0.20, 0.40, 1.0]
EXPECTED_METRICS = ["tau_onset", "sync_auc", "phase_lag"]
EXPECTED_N_SEEDS = 20
EXPECTED_N_BOOTSTRAP = 16
EXPECTED_BASE_SEED = 42
EXPECTED_NULL_SEED_OFFSET_M1 = 10000
EXPECTED_NULL_SEED_M3 = 12345

LOCKED_TIER_STRINGS = frozenset(
    {
        "SYNTHETIC_GATE6_CERTIFIED_D002H_REDESIGN",
        "MARGINAL_PASS_SYNTHETIC_D002H",
        "D002H_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET",
        "REFUSED_NULL_AUDIT_FAIL_D002H",
    }
)
LOCKED_AGGREGATE_VERDICTS = frozenset({"PASS", "FAIL", "MARGINAL_PASS", "REFUSED"})


def _load_verdict() -> dict[str, Any]:
    """Load + parse the top-level canonical verdict capsule."""
    raw = CANONICAL_VERDICT_PATH.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise AssertionError(
            f"canonical verdict root must be a JSON object; got {type(parsed).__name__}"
        )
    return cast(dict[str, Any], parsed)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_run_artifact_exists() -> None:
    """The top-level canonical-run verdict capsule exists on disk."""
    msg_path = f"top-level canonical verdict capsule must exist at {CANONICAL_VERDICT_RELPATH}"
    assert CANONICAL_VERDICT_PATH.exists(), msg_path

    # Second assertion: file is non-empty + parses as JSON.
    raw = CANONICAL_VERDICT_PATH.read_text(encoding="utf-8")
    msg_nonempty = "canonical verdict capsule must be non-empty"
    assert raw.strip(), msg_nonempty
    parsed = json.loads(raw)
    msg_dict = "canonical verdict capsule root must be a JSON object"
    assert isinstance(parsed, dict), msg_dict


def test_canonical_run_schema_version() -> None:
    """Schema version is the locked D002H-CANONICAL-RUN-VERDICT-v1 tag."""
    v = _load_verdict()
    msg_schema = f"schema_version must be {EXPECTED_SCHEMA!r}; got {v.get('schema_version')!r}"
    assert v.get("schema_version") == EXPECTED_SCHEMA, msg_schema
    msg_study = f"study_id must be {EXPECTED_STUDY_ID!r}"
    assert v.get("study_id") == EXPECTED_STUDY_ID, msg_study
    msg_run = f"run_id must be {EXPECTED_RUN_ID!r}"
    assert v.get("run_id") == EXPECTED_RUN_ID, msg_run


def test_canonical_run_grid_matches_d002h_prereg() -> None:
    """Grid matches D-002H prereg verbatim (no retroactive grid edit)."""
    v = _load_verdict()
    grid = v.get("grid")
    msg_grid = "verdict must carry a 'grid' field"
    assert isinstance(grid, dict), msg_grid

    msg_sub = "grid.substrates must be ['ricci_flow']"
    assert grid.get("substrates") == ["ricci_flow"], msg_sub

    msg_N = f"grid.N must equal {EXPECTED_N_GRID}"
    assert grid.get("N") == EXPECTED_N_GRID, msg_N

    msg_lam = f"grid.lambda_values must equal {EXPECTED_LAMBDA_GRID}"
    assert grid.get("lambda_values") == EXPECTED_LAMBDA_GRID, msg_lam

    msg_seeds = f"grid.n_seeds must equal {EXPECTED_N_SEEDS}"
    assert grid.get("n_seeds") == EXPECTED_N_SEEDS, msg_seeds

    msg_boot = f"grid.n_bootstrap must equal {EXPECTED_N_BOOTSTRAP}"
    assert grid.get("n_bootstrap") == EXPECTED_N_BOOTSTRAP, msg_boot

    msg_tot = "grid.total_cells_canonical must equal 18"
    assert grid.get("total_cells_canonical") == 18, msg_tot

    # Reproducibility seeds locked
    repro = v.get("reproducibility")
    msg_repro = "verdict must carry a 'reproducibility' field"
    assert isinstance(repro, dict), msg_repro
    msg_base = f"reproducibility.base_seed must equal {EXPECTED_BASE_SEED}"
    assert repro.get("base_seed") == EXPECTED_BASE_SEED, msg_base
    msg_m1 = f"reproducibility.null_seed_offset_M1 must equal {EXPECTED_NULL_SEED_OFFSET_M1}"
    assert repro.get("null_seed_offset_M1") == EXPECTED_NULL_SEED_OFFSET_M1, msg_m1
    msg_m3 = f"reproducibility.null_seed_M3 must equal {EXPECTED_NULL_SEED_M3}"
    assert repro.get("null_seed_M3") == EXPECTED_NULL_SEED_M3, msg_m3


def test_canonical_run_uses_only_m1_m3_nulls() -> None:
    """Null mechanisms are exactly {M1, M3}; M6 (R2-B) is structurally
    excluded per D002H_R2B_INAPPLICABILITY_NOTE.md."""
    v = _load_verdict()
    nulls = v.get("null_mechanisms_used")
    msg_list = "null_mechanisms_used must be a list"
    assert isinstance(nulls, list), msg_list
    msg_set = "null_mechanisms_used must equal ['M1_INDEPENDENT_SEED', 'M3_TOPOLOGY_CONDITIONED']"
    assert set(nulls) == {
        "M1_INDEPENDENT_SEED",
        "M3_TOPOLOGY_CONDITIONED",
    }, msg_set
    msg_no_m6 = "null_mechanisms_used must NOT contain M6 (R2-B inapplicable)"
    assert "M6_PLACEBO_COUPLING" not in nulls, msg_no_m6


def test_canonical_run_r2b_marked_inapplicable() -> None:
    """Acceptance conjunction is the 4-term form (R1 AND R2 AND R3 AND
    NULL_AUDIT). R2-B is INAPPLICABLE under D-002H scope."""
    v = _load_verdict()
    conj = v.get("acceptance_conjunction", "")
    msg_str = "acceptance_conjunction must be a non-empty string"
    assert isinstance(conj, str) and conj, msg_str
    msg_r1 = "acceptance_conjunction must reference R1"
    assert "R1" in conj, msg_r1
    msg_r2 = "acceptance_conjunction must reference R2"
    assert "R2" in conj, msg_r2
    msg_r3 = "acceptance_conjunction must reference R3"
    assert "R3" in conj, msg_r3
    msg_audit = "acceptance_conjunction must reference NULL_AUDIT"
    assert "NULL_AUDIT" in conj, msg_audit
    msg_inappl = "acceptance_conjunction must mark R2-B INAPPLICABLE"
    assert "R2-B" in conj and "INAPPLICABLE" in conj, msg_inappl


def test_canonical_run_per_cell_verdict_count_18() -> None:
    """n_cells_total == 18, and cell summary counts sum to 18."""
    v = _load_verdict()
    msg_total = "n_cells_total must equal 18"
    assert v.get("n_cells_total") == 18, msg_total

    n_pass = int(v.get("n_cells_pass", 0))
    n_fail = int(v.get("n_cells_fail", 0))
    n_indet = int(v.get("n_cells_indeterminate", 0))
    msg_sum = (
        f"n_cells_pass({n_pass}) + n_cells_fail({n_fail}) + "
        f"n_cells_indeterminate({n_indet}) must equal 18"
    )
    assert n_pass + n_fail + n_indet == 18, msg_sum


def test_canonical_run_tier_string_in_locked_enum() -> None:
    """tier_string + aggregate_verdict are both in their locked enums."""
    v = _load_verdict()
    tier = v.get("tier_string")
    msg_tier = f"tier_string {tier!r} must be one of {sorted(LOCKED_TIER_STRINGS)}"
    assert tier in LOCKED_TIER_STRINGS, msg_tier

    agg = v.get("aggregate_verdict")
    msg_agg = f"aggregate_verdict {agg!r} must be one of {sorted(LOCKED_AGGREGATE_VERDICTS)}"
    assert agg in LOCKED_AGGREGATE_VERDICTS, msg_agg


def test_canonical_run_aggregate_verdict_consistent_with_cells() -> None:
    """aggregate_verdict <-> tier_string <-> cell counts must be consistent."""
    v = _load_verdict()
    tier = v.get("tier_string")
    agg = v.get("aggregate_verdict")
    n_pass = int(v.get("n_cells_pass", 0))
    guards = v.get("anti_overclaim_guards", {})
    null_audit_fail = bool(guards.get("null_audit_fail"))
    marginal_pass = bool(guards.get("marginal_pass"))

    if null_audit_fail:
        msg_refused = "null_audit_fail=True must imply tier=REFUSED_*"
        assert tier == "REFUSED_NULL_AUDIT_FAIL_D002H", msg_refused
        msg_agg_ref = "null_audit_fail=True must imply aggregate_verdict=REFUSED"
        assert agg == "REFUSED", msg_agg_ref
    elif n_pass == 0:
        msg_fail_tier = (
            "0 passing cells (no null audit fail) must imply "
            "tier=D002H_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET"
        )
        assert tier == "D002H_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET", msg_fail_tier
        msg_fail_agg = "0 passing cells must imply aggregate_verdict=FAIL"
        assert agg == "FAIL", msg_fail_agg
    elif marginal_pass:
        msg_marg_tier = "marginal_pass=True must imply tier=MARGINAL_PASS_SYNTHETIC_D002H"
        assert tier == "MARGINAL_PASS_SYNTHETIC_D002H", msg_marg_tier
        msg_marg_agg = "marginal_pass=True must imply aggregate_verdict=MARGINAL_PASS"
        assert agg == "MARGINAL_PASS", msg_marg_agg
    else:
        msg_pass_tier = (
            f"n_pass={n_pass} clean must imply tier=SYNTHETIC_GATE6_CERTIFIED_D002H_REDESIGN"
        )
        assert tier == "SYNTHETIC_GATE6_CERTIFIED_D002H_REDESIGN", msg_pass_tier
        msg_pass_agg = "clean pass must imply aggregate_verdict=PASS"
        assert agg == "PASS", msg_pass_agg


def test_canonical_run_preserves_d002c_ledger() -> None:
    """D-002C claim ledger split-anchor check after PR #692 REFUSED append.

    Live disk sha matches the post-append anchor (PR #692 legitimate
    append); the canonical-run verdict capsule's frozen
    ``d002c_ledger_sha_at_run`` field equals the pre-append anchor
    (sha at canonical-sweep execution time, PR #691 — before the
    legitimate ledger append). The capsule remains a faithful
    historical record of the run; live disk rotates per the append
    contract.
    """
    # Live file sha must equal post-append anchor.
    actual_sha = _sha256_file(REPO_ROOT / D002C_LEDGER_RELPATH)
    msg_live = (
        f"D-002C claim ledger live sha drift: expected post-append anchor "
        f"{D002C_LEDGER_SHA_PIN} (after PR #692 append), got {actual_sha}"
    )
    assert actual_sha == D002C_LEDGER_SHA_PIN, msg_live

    v = _load_verdict()
    msg_flag = (
        "verdict.d002c_ledger_touched must be False (the sweep itself did not touch the ledger)"
    )
    assert v.get("d002c_ledger_touched") is False, msg_flag
    msg_pin = (
        f"verdict.d002c_ledger_sha_at_run must equal the pre-append anchor "
        f"{D002C_LEDGER_SHA_PRE_APPEND} — this is the sha the ledger had at "
        "canonical-sweep execution time (PR #691); the artifact is a frozen "
        "historical record and is not rotated by the subsequent PR #692 append."
    )
    assert v.get("d002c_ledger_sha_at_run") == D002C_LEDGER_SHA_PRE_APPEND, msg_pin

    # Governance docs byte-exact UNCHANGED.
    prereg_sha = _sha256_file(REPO_ROOT / D002H_PREREG_RELPATH)
    msg_prereg = (
        f"D-002H prereg sha256 must equal pinned anchor; "
        f"expected {D002H_PREREG_SHA_PIN}, got {prereg_sha}"
    )
    assert prereg_sha == D002H_PREREG_SHA_PIN, msg_prereg
    acc_sha = _sha256_file(REPO_ROOT / D002G_ACCEPTANCE_RELPATH)
    msg_acc = (
        f"D-002G acceptance rules sha256 must equal pinned anchor; "
        f"expected {D002G_ACCEPTANCE_SHA_PIN}, got {acc_sha}"
    )
    assert acc_sha == D002G_ACCEPTANCE_SHA_PIN, msg_acc


def test_canonical_run_anti_overclaim_guards_applied() -> None:
    """anti_overclaim_guards block has the three documented flags
    (marginal_pass, single_path_pass, null_audit_fail) and the triggered
    list mirrors those flags."""
    v = _load_verdict()
    guards = v.get("anti_overclaim_guards")
    msg_dict = "anti_overclaim_guards must be a dict"
    assert isinstance(guards, dict), msg_dict
    msg_marg = "anti_overclaim_guards.marginal_pass must be a bool"
    assert isinstance(guards.get("marginal_pass"), bool), msg_marg
    msg_single = "anti_overclaim_guards.single_path_pass must be a bool"
    assert isinstance(guards.get("single_path_pass"), bool), msg_single
    msg_audit = "anti_overclaim_guards.null_audit_fail must be a bool"
    assert isinstance(guards.get("null_audit_fail"), bool), msg_audit

    triggered = v.get("anti_overclaim_guards_triggered")
    msg_trig_list = "anti_overclaim_guards_triggered must be a list"
    assert isinstance(triggered, list), msg_trig_list

    # Consistency: every triggered name must map back to a True flag.
    valid_names = {"MARGINAL_PASS", "SINGLE_PATH_PASS", "NULL_AUDIT_FAIL"}
    msg_names = f"triggered guard names must be a subset of {sorted(valid_names)}"
    assert set(triggered).issubset(valid_names), msg_names

    msg_marg_round = "if marginal_pass=True then 'MARGINAL_PASS' must be in triggered"
    if guards.get("marginal_pass"):
        assert "MARGINAL_PASS" in triggered, msg_marg_round
    msg_audit_round = "if null_audit_fail=True then 'NULL_AUDIT_FAIL' must be in triggered"
    if guards.get("null_audit_fail"):
        assert "NULL_AUDIT_FAIL" in triggered, msg_audit_round


def test_canonical_run_anchor_main_sha_pinned() -> None:
    """Top-level verdict pins anchor_main_sha = ee12a9e6... (R2-B merge)."""
    v = _load_verdict()
    msg_anchor = f"anchor_main_sha must equal {ANCHOR_MAIN_SHA}; got {v.get('anchor_main_sha')!r}"
    assert v.get("anchor_main_sha") == ANCHOR_MAIN_SHA, msg_anchor
    msg_scope = "scope must declare 'ricci_flow substrate only' (no cross-substrate generalisation)"
    assert "ricci_flow" in v.get("scope", "").lower(), msg_scope
    # Scope note must explicitly forbid cross-substrate generalisation.
    note = v.get("scope_note", "")
    msg_note = "scope_note must mention block_structured/temporal_coupling are NOT in scope"
    assert "block_structured" in note and "temporal_coupling" in note, msg_note


def test_canonical_run_bonferroni_denominator_locked() -> None:
    """Bonferroni denominator is 216 (inherited verbatim from D-002G);
    per-cell alpha is 0.05/216."""
    v = _load_verdict()
    msg_bonf = (
        "bonferroni_n_cells must equal 216 (inherited from D-002G); "
        f"got {v.get('bonferroni_n_cells')!r}"
    )
    assert v.get("bonferroni_n_cells") == 216, msg_bonf
    eff_alpha = v.get("effective_alpha_per_cell")
    msg_alpha = "effective_alpha_per_cell must equal 0.05/216 to float tolerance"
    assert isinstance(eff_alpha, (int, float)), msg_alpha
    assert abs(float(eff_alpha) - 0.05 / 216.0) < 1e-12, msg_alpha
